"""Локальный сервер для визуала: статика ui/, фид и мини-API. Слушает только 127.0.0.1."""
import json
import os
import shutil
import stat
import string
import subprocess
import sys
import threading
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import config, github as gh, resurrect as resurrect_mod, readme_gen, runner
from .disk import JUNK_DIRS
from .doctor import diagnose
from .index import build_feed, read_feed, summarize, write_feed, node as galaxy_node
from .scanner import scan
from .store import (all_meta, diff_scans, get_meta, history_for, list_projects, norm_root,
                    prev_scores, save_projects, set_note, set_tags)

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}
MAX_BODY = 64 * 1024

# Шаблоны .gitignore по стекам — для кнопки «крестить git'ом»
GITIGNORE_TEMPLATES = {
    "python": "__pycache__/\n*.pyc\n.venv/\nvenv/\n.env\n*.log\n.pytest_cache/\n.mypy_cache/\n",
    "node": "node_modules/\n.next/\nout/\ndist/\n.env\n*.log\n",
    "csharp": "bin/\nobj/\n*.user\n.vs/\n",
    "go": "bin/\nvendor/\n",
    "js": "node_modules/\ndist/\n.env\n*.log\n",
    "docker": "",
    "git": "",
}
GITIGNORE_COMMON = ".DS_Store\nThumbs.db\n"


def _within(path, root) -> bool:
    """Разрешаем открывать только то, что внутри корня сканирования."""
    if path is None or not str(path).strip():
        return False                                  # пустой путь превратился бы в cwd процесса
    try:
        target = os.path.abspath(str(path).strip())
        base = os.path.abspath(str(root))
    except (TypeError, ValueError):
        return False
    if target == base:
        return True
    try:
        return os.path.commonpath([target, base]) == base
    except ValueError:
        return False                                   # на Windows: пути на разных дисках


class ScanState:
    """Один фоновый скан за раз: UI получает ответ мгновенно и опрашивает статус.
    Синхронный скан большого диска жил дольше таймаута браузера — отсюда «Failed to fetch»."""

    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.root = None
        self.error = None

    def start(self, root, work) -> bool:
        """True — джоба запущена; False — уже идёт другой скан (409 в UI)."""
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.root = root
            self.error = None

        def run():
            try:
                work()
            except Exception as exc:                        # noqa: BLE001 — статус уйдёт в UI
                self.error = f"скан не удался: {exc}"
            finally:
                with self._lock:
                    self.running = False

        threading.Thread(target=run, daemon=True).start()
        return True

    def status(self) -> dict:
        with self._lock:
            return {"running": self.running, "root": self.root, "error": self.error}


class ResurrectState:
    """Один воскрешающий поток за раз: этапы и лог читает UI через /api/resurrect-status."""

    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.path = None
        self.stage = ""
        self.log = deque(maxlen=120)
        self.error = None

    def start(self, path, work) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.path = path
            self.stage = "старт"
            self.log.clear()
            self.error = None

        def run():
            try:
                work(self._say)
            except Exception as exc:                    # noqa: BLE001 — статус уйдёт в UI
                self.error = f"воскрешение не удалось: {exc}"
            finally:
                with self._lock:
                    self.running = False

        threading.Thread(target=run, daemon=True).start()
        return True

    def _say(self, text, stage=None):
        with self._lock:
            self.log.append(str(text))
            if stage:
                self.stage = stage

    def snapshot(self) -> dict:
        with self._lock:
            return {"running": self.running, "path": self.path, "stage": self.stage,
                    "log": list(self.log)[-40:], "error": self.error}


class RunRegistry:
    """Запущенные процессы проектов: путь -> {proc, cmd, log}. Лог копится фоновым читателем."""

    def __init__(self):
        self._lock = threading.Lock()
        self.procs = {}

    def start(self, path, cmd) -> dict:
        with self._lock:
            old = self.procs.get(path)
            if old and old["proc"].poll() is None:
                return {"error": "этот проект уже запущен — сначала останови"}
            log = deque(maxlen=200)
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as exc:
                return {"error": f"не запустилось: {exc}"}
            self.procs[path] = {"proc": proc, "cmd": cmd, "log": log, "exit": None}

        def pump():
            for line in proc.stdout:
                with self._lock:
                    log.append(str(line).rstrip()[:160])
            with self._lock:
                entry = self.procs.get(path)
                if entry and entry["proc"] is proc:
                    entry["exit"] = proc.wait()

        threading.Thread(target=pump, daemon=True).start()
        return {"pid": proc.pid, "cmd": cmd}

    def snapshot(self, path) -> dict:
        with self._lock:
            entry = self.procs.get(path)
            if not entry:
                return {"running": False}
            running = entry["proc"].poll() is None
            return {"running": running, "cmd": entry["cmd"],
                    "log": list(entry["log"])[-40:], "exit": entry["exit"]}

    def stop(self, path) -> bool:
        with self._lock:
            entry = self.procs.get(path)
            if not entry or entry["proc"].poll() is not None:
                return False
            entry["proc"].terminate()
            return True


class ButlerHTTPServer(ThreadingHTTPServer):
    """На Windows http.server разрешает двойной биндинг порта (allow_reuse_address=1).
    Нам второй экземпляр не нужен никогда — пусть громко падает при старте."""
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.butler_scan = ScanState()
        self.butler_resurrect = ResurrectState()
        self.butler_runs = RunRegistry()


def _list_drives() -> list:
    """Доступные диски A–Z: перебор дешёвый, зато без win32-API зависимостей."""
    return [d + ":\\" for d in string.ascii_uppercase if os.path.isdir(d + ":\\")]


def _browse(path: str) -> dict:
    """Содержимое папки для пикера в UI: без файлов, симлинок и системного мусора."""
    raw = (path or "").strip()
    if not raw:
        return {"path": "", "parent": None, "drives": _list_drives(), "dirs": []}
    if len(raw) == 2 and raw.endswith(":"):
        raw += "\\"                               # голый "C:" — это cwd диска, а не корень
    try:
        base = Path(raw).resolve(strict=True)
    except (OSError, RuntimeError):
        return {"error": f"Папка не найдена: {raw}"}
    if not base.is_dir():
        return {"error": f"Это не папка: {raw}"}
    try:
        children = sorted(base.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        return {"error": f"Не прочиталось: {exc}"}
    dirs = []
    for child in children:
        name = child.name
        if name.startswith((".", "$")) or name.lower() == "system volume information":
            continue
        try:
            if child.is_symlink() or not child.is_dir():
                continue
            attrs = getattr(os.stat(child, follow_symlinks=False), "st_file_attributes", 0)
        except OSError:
            continue                              # недоступное — просто не показываем
        if attrs & (getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) |
                    getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)):
            continue
        dirs.append(name)
        if len(dirs) >= 800:                      # патологические папки не утащим в JSON целиком
            break
    parent = str(base.parent) if base.parent != base else None
    return {"path": str(base), "parent": parent, "drives": _list_drives(), "dirs": dirs}


class ButlerHandler(BaseHTTPRequestHandler):
    server_version = "ProjectButler/0.2"
    protocol_version = "HTTP/1.1"

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code=200):
        self._send(code, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))

    def _error(self, code, message):
        self._json({"error": message}, code)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8", errors="replace"))
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def root(self) -> str:
        return getattr(self.server, "butler_root", config.resolve_root())

    def log_message(self, fmt, *args):                   # тихий лог: не спамим на каждый файл
        if "404" in str(args):
            sys.stderr.write("butler-ui: " + (fmt % args) + "\n")

    def _static(self, name):
        target = (UI_DIR / name).resolve()
        if not str(target).startswith(str(UI_DIR.resolve())) or not target.is_file():
            return self._error(404, "Файл не найден")
        ctype = STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
        return self._send(200, target.read_bytes(), ctype)

    def _rebuild_feed(self):
        root = norm_root(self.root)
        feed = build_feed(root, list_projects(root))
        write_feed(config.FEED_PATH, feed)
        return feed

    # ---------- маршруты ----------
    def do_GET(self):                                    # noqa: N802 — так требует http.server
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/ui/galaxy.html"):
            return self._static("galaxy.html")
        if path.startswith("/ui/"):
            return self._static(os.path.basename(path))
        if path.lstrip("/") in ("galaxy.js", "galaxy.css", "favicon.ico"):
            # запасной маршрут: если страницу открыли не с / — относительные src не ломаются
            return self._static(os.path.basename(path))
        if path == "/galaxy.json":
            feed = read_feed(config.FEED_PATH)
            if feed is None:
                feed = self._rebuild_feed()
            feed["prev"] = prev_scores(norm_root(self.root))   # score с прошлого скана — для сверхновых
            feed["meta"] = all_meta()                          # теги и заметки — для фильтров и карточек
            return self._json(feed)
        if path == "/api/meta":
            target = (parse_qs(urlsplit(self.path).query).get("path") or [""])[0]
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            return self._json({"path": target, **get_meta(target)})
        if path == "/api/search":
            q = (parse_qs(urlsplit(self.path).query).get("q") or [""])[0].strip().lower()
            return self._json({"q": q, "results": self._search_content(q)})
        if path == "/api/digest":
            return self._json(self._digest())
        if path == "/api/feed-version":
            try:
                mtime = os.path.getmtime(config.FEED_PATH)
            except OSError:
                mtime = 0.0
            return self._json({"mtime": mtime, "root": self.root})
        if path == "/api/resurrect-status":
            target = (parse_qs(urlsplit(self.path).query).get("path") or [""])[0]
            snap = self.server.butler_resurrect.snapshot()
            if target and snap["path"] and norm_root(target) != snap["path"]:
                snap = {"running": False}                      # спросили про другой проект
            return self._json(snap)
        if path == "/api/run-status":
            target = (parse_qs(urlsplit(self.path).query).get("path") or [""])[0]
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            return self._json(self.server.butler_runs.snapshot(target))
        if path == "/api/health":
            return self._json({"ok": True, "root": self.root, "feed": str(config.FEED_PATH)})
        if path == "/api/projects":
            root = norm_root(self.root)
            records = list_projects(root)
            return self._json({"root": root, "count": len(records),
                               "projects": [galaxy_node(r, root) for r in records]})
        if path == "/api/stacks":
            root = norm_root(self.root)
            nodes = [galaxy_node(r, root) for r in list_projects(root)]
            return self._json(summarize(nodes))
        if path == "/api/roots":
            return self._json({"current": self.root, "roots": config.known_roots()})
        if path == "/api/scan-status":
            return self._json(self.server.butler_scan.status())
        if path == "/api/browse":
            target = (parse_qs(urlsplit(self.path).query).get("path") or [""])[0]
            data = _browse(target)
            if "error" in data:
                return self._error(400, data["error"])
            return self._json(data)
        if path == "/api/diff":
            return self._json(diff_scans(norm_root(self.root)))
        if path == "/api/history":
            target = (parse_qs(urlsplit(self.path).query).get("path") or [""])[0]
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            return self._json({"path": target, "history": history_for(target)})
        if path == "/api/settings":
            return self._json(config.load_settings())
        if path == "/api/gh/status":
            token = gh.get_token()
            if not token:
                return self._json({"authed": False})
            who = gh.validate_token(token)
            if not who.get("ok"):
                return self._json({"authed": False, "stale": True, "error": who.get("error")})
            return self._json({"authed": True, "login": who["login"],
                               "name": who["name"], "avatar": who["avatar"]})
        if path == "/api/gh/repo":
            target = (parse_qs(urlsplit(self.path).query).get("path") or [""])[0]
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            remote = gh.remote_url(target)
            owner_repo = gh.parse_remote(remote)
            out = {"has_git": os.path.isdir(os.path.join(target, ".git")),
                   "remote": remote, "owner_repo": owner_repo, "authed": bool(gh.get_token())}
            if owner_repo and gh.get_token():
                info = gh.repo_info(owner_repo, gh.get_token())
                if info.get("ok"):
                    out.update({k: info[k] for k in ("private", "html_url", "description",
                                                     "has_issues", "has_wiki")})
                    out["on_github"] = True
            return self._json(out)
        return self._error(404, f"Нет такого маршрута: {path}")

    def do_POST(self):                                   # noqa: N802
        path = self.path.split("?", 1)[0]
        args = self._body()
        if path == "/api/root":
            new_root = str(args.get("root") or "").strip()
            if not new_root:
                return self._error(400, "Путь пустой — укажи папку")
            if not os.path.isdir(new_root):
                return self._error(400, f"Папка не найдена: {new_root}")
            new_root = norm_root(new_root)

            def switch_work():
                save_projects(scan(new_root), new_root)
                config.remember_root(new_root)
                feed = build_feed(new_root, list_projects(new_root))
                write_feed(config.FEED_PATH, feed)
                self.server.butler_root = new_root      # сервер смотрит туда, куда выбрал пользователь

            if not self.server.butler_scan.start(new_root, switch_work):
                return self._error(409, "Скан уже идёт — дождись окончания")
            return self._json({"ok": True, "root": new_root, "scanning": True})
        if path == "/api/scan":
            root = norm_root(args.get("root") or self.root)
            if not os.path.isdir(root):
                return self._error(400, f"Папка не найдена: {root}")

            def rescan_work():
                save_projects(scan(root), root)
                config.remember_root(root)
                feed = build_feed(root, list_projects(root))
                write_feed(config.FEED_PATH, feed)
                if root == norm_root(self.root):
                    self.server.butler_root = root

            if not self.server.butler_scan.start(root, rescan_work):
                return self._error(409, "Скан уже идёт — дождись окончания")
            return self._json({"ok": True, "root": root, "scanning": True})
        if path == "/api/open":
            target = args.get("path") or ""
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            how = (args.get("with") or "explorer").lower()
            try:
                note = _open_target(target, how)
            except OSError as exc:
                return self._error(500, f"Не открылось: {exc}")
            return self._json({"ok": True, "opened": target, "how": how, "note": note})
        if path == "/api/doctor":
            target = args.get("path") or ""
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            rec = self._rec_for(target)
            if rec is None:
                return self._error(404, "Проект не найден в базе — пересканируй")
            return self._json({"ok": True, "project": rec["name"], "checks": diagnose(rec)})
        if path == "/api/gitinit":
            return self._git_init(args)
        if path == "/api/clean":
            return self._clean_junk(args)
        if path == "/api/tags":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            tags = set_tags(target, args.get("tags") or [])
            return self._json({"ok": True, "path": target, "tags": tags})
        if path == "/api/note":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            note = set_note(target, args.get("note") or "")
            return self._json({"ok": True, "path": target, "note": note})
        if path == "/api/resurrect":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            if not os.path.isdir(target):
                return self._error(400, f"Папка не найдена: {target}")
            rec = self._rec_for(target)
            if rec is None:
                return self._error(404, "Проект не найден в базе — пересканируй")
            if args.get("confirm") is not True:
                return self._json({"ok": True, "plan": resurrect_mod.plan(target, rec["stacks"])})
            stacks = rec.get("stacks", []) or []
            root = target
            state = self.server.butler_resurrect
            if not state.start(norm_root(target),
                               lambda log: resurrect_mod.resurrect(root, stacks, log)):
                return self._error(409, "Воскрешение уже идёт — дождись окончания")
            return self._json({"ok": True, "path": target, "running": True})
        if path == "/api/run":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            rec = self._rec_for(target)
            if args.get("confirm") is not True:
                plan = runner.detect_command(target, rec.get("stacks", [])) if rec else None
                return self._json({"ok": True, "cmd": plan["cmd"] if plan else None,
                                   "kind": plan["kind"] if plan else None})
            cmd = args.get("cmd")
            if not cmd:
                plan = runner.detect_command(target, rec.get("stacks", [])) if rec else None
                if not plan:
                    return self._error(400, "Не понял, чем запускать проект — запусти вручную")
                cmd = plan["cmd"]
            result = self.server.butler_runs.start(target, cmd)
            if "error" in result:
                return self._error(409, result["error"])
            return self._json({"ok": True, "path": target, **result})
        if path == "/api/run-stop":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            if self.server.butler_runs.stop(target):
                return self._json({"ok": True, "path": target, "stopped": True})
            return self._error(404, "Запущенного процесса этого проекта нет")
        if path == "/api/readme":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            rec = self._rec_for(target)
            if rec is None:
                return self._error(404, "Проект не найден в базе — пересканируй")
            plan = runner.detect_command(target, rec.get("stacks", []))
            result = readme_gen.generate(target, rec, plan)
            return self._json({"ok": True, "path": target, **result})
        if path == "/api/settings":
            return self._json(config.save_settings(args))
        if path == "/api/gh/login":
            token = str(args.get("token") or "").strip()
            if not token:
                return self._error(400, "Вставь Personal Access Token с правами repo")
            who = gh.validate_token(token)
            if not who.get("ok"):
                return self._error(401, who.get("error", "токен не принят"))
            gh.save_token(token)
            return self._json({"ok": True, "login": who["login"], "name": who["name"],
                               "avatar": who["avatar"]})
        if path == "/api/gh/logout":
            gh.clear_token()
            return self._json({"ok": True})
        if path == "/api/gh/publish":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            result = gh.publish(target, str(args.get("name") or ""),
                                bool(args.get("private")), gh.get_token(),
                                lambda t: None)
            if not result.get("ok"):
                return self._error(400, result.get("error", "публикация не удалась"))
            return self._json({"ok": True, **result})
        if path == "/api/gh/repo-settings":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            remote = gh.parse_remote(gh.remote_url(target))
            if not remote:
                return self._error(400, "у проекта нет GitHub-remote — сначала опубликуй")
            result = gh.repo_settings(remote, gh.get_token(), args)
            if not result.get("ok"):
                return self._error(400, result.get("error", "настройки не применились"))
            return self._json({"ok": True, **result})
        if path == "/api/gh/release":
            target = str(args.get("path") or "")
            if not _within(target, self.root):
                return self._error(403, "Путь вне корня сканирования — отказ")
            remote = gh.parse_remote(gh.remote_url(target))
            if not remote:
                return self._error(400, "у проекта нет GitHub-remote — сначала опубликуй")
            tag = str(args.get("tag") or "").strip()
            if not tag:
                return self._error(400, "укажи тег релиза, например v1.0.0")
            result = gh.create_release(remote, gh.get_token(), tag,
                                       str(args.get("name") or ""),
                                       str(args.get("body") or ""),
                                       str(args.get("target") or ""))
            if not result.get("ok"):
                return self._error(400, result.get("error", "релиз не создался"))
            return self._json({"ok": True, **result})
        return self._error(404, f"Нет такого маршрута: {path}")

    # ---------- чтение для API ----------

    def _rec_for(self, target):
        """Запись проекта по пути; прямые слеши нормализуем, иначе база не узнает свой проект."""
        want = norm_root(target)
        return next((r for r in list_projects(norm_root(self.root))
                     if r["path"] == want), None)

    def _search_content(self, q):
        """Поиск по имени, стеку, зависимостям и README — то, чего нет в локальном фильтре."""
        if len(q) < 2:
            return []
        out = []
        for rec in list_projects(norm_root(self.root)):
            name = rec.get("name", "")
            stacks = " ".join(rec.get("stacks", []) or []).lower()
            facts = rec.get("facts") or {}
            deps = [str(d).lower() for d in (facts.get("deps") or [])]
            where = None
            if q in name.lower():
                where = "имя"
            elif q in stacks:
                where = "стек"
            elif any(q in d for d in deps):
                where = "зависимости: " + ", ".join(d for d in deps if q in d)[:80]
            elif rec.get("has_readme"):
                try:
                    with open(os.path.join(rec["path"], "README.md"), "r",
                              encoding="utf-8", errors="replace") as fh:
                        head = fh.read(4096).lower()
                    if q in head:
                        where = "README"
                except OSError:
                    pass
            if not where:
                for t in (facts.get("todos") or []):
                    if q in str(t.get("text", "")).lower():
                        where = "TODO " + str(t.get("file", "")) + ":" + str(t.get("line", ""))
                        break
            if where:
                out.append({"name": name, "path": rec["path"], "where": where})
            if len(out) >= 20:
                break
        return out

    def _digest(self):
        """Что изменилось с прошлого скана + пара цифр для контекста."""
        root = norm_root(self.root)
        records = list_projects(root)
        junk = sum(int(((r.get("facts") or {}).get("disk") or {}).get("junk", 0) or 0)
                   for r in records)
        secrets = sum(int((r.get("facts") or {}).get("secret_count", 0) or 0) for r in records)
        todos = sum(int(r.get("todo_count", 0) or 0) for r in records)
        return {"root": root, "projects": len(records), "junk_bytes": junk,
                "secrets": secrets, "todos": todos, "diff": diff_scans(root)}

    # ---------- действия (мутируют диск) ----------
    def _git_init(self, args):
        target = args.get("path") or ""
        if not _within(target, self.root):
            return self._error(403, "Путь вне корня сканирования — отказ")
        if args.get("confirm") is not True:
            return self._error(400, "Нужно подтверждение: {\"confirm\": true}")
        if (Path(target) / ".git").exists():
            return self._error(400, "git тут уже есть")
        git = shutil.which("git")
        if not git:
            return self._error(500, "git не найден в PATH")
        rec = self._rec_for(target)
        stacks = (rec or {}).get("stacks", [])
        ignore = GITIGNORE_COMMON + "".join(GITIGNORE_TEMPLATES.get(st, "") for st in stacks)
        gitignore = Path(target) / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(ignore, encoding="utf-8")
        steps = []
        for cmd in ([git, "init", "-b", "main"],
                    [git, "add", "-A"],
                    [git, "-c", "user.name=Project Butler",
                     "-c", "user.email=butler@localhost",
                     "commit", "-m", "chore: initial commit (via Project Butler)",
                     "--no-gpg-sign"]):
            try:
                proc = subprocess.run(cmd, cwd=target, capture_output=True, text=True,
                                      timeout=120, encoding="utf-8", errors="replace")
            except (OSError, subprocess.TimeoutExpired) as exc:
                return self._error(500, f"{' '.join(cmd[1:3])}: {exc}")
            steps.append({"cmd": " ".join(cmd[1:3]), "code": proc.returncode})
            if proc.returncode != 0:
                return self._json({"ok": False, "steps": steps,
                                   "error": (proc.stderr or proc.stdout).strip()[:400]}, 500)
        return self._json({"ok": True, "steps": steps, "gitignore": ignore})

    def _clean_junk(self, args):
        target = args.get("path") or ""
        part = args.get("part") or ""
        if part not in JUNK_DIRS:
            return self._error(400, f"Не белый список мусора: {part!r}")
        full = os.path.join(target, part)
        if not _within(full, self.root):
            return self._error(403, "Путь вне корня сканирования — отказ")
        if args.get("confirm") is not True:
            return self._error(400, "Нужно подтверждение: {\"confirm\": true}")
        if not os.path.isdir(full):
            return self._error(404, f"Нет такой папки: {full}")
        size = 0
        for dirpath, _dirs, files in os.walk(full):
            for name in files:
                try:
                    size += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    continue
        try:
            shutil.rmtree(full, ignore_errors=False)
        except OSError as exc:
            return self._error(500, f"Не удалилось: {exc}")
        return self._json({"ok": True, "removed": full, "freed_bytes": size})


def _code_launcher():
    """Честный запускатель VS Code.

    `code` на Windows — это .cmd-прокладка, голый Popen её не исполняет (WinError 2).
    Плюс PATH может быть перехвачен форками (Cursor тоже ставит свой `code`).
    Порядок: .cmd-прокладки из PATH с «Microsoft VS Code» в пути → их родительский
    Code.exe → любая другая прокладка через cmd /c → стандартные пути установки.
    """
    shims = []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip().strip('"')
        if not d:
            continue
        for name in ("code.cmd", "code.bat"):
            cand = os.path.join(d, name)
            if os.path.isfile(cand):
                shims.append(cand)
    preferred = [s for s in shims if "microsoft vs code" in s.lower()]
    for shim in preferred:
        base = os.path.dirname(shim)
        for _ in range(3):                              # bin/ → корень установки
            base = os.path.dirname(base)
            exe = os.path.join(base, "Code.exe")
            if os.path.isfile(exe):
                return [exe]
    if preferred:
        return ["cmd", "/c", preferred[0]]
    if shims:
        return ["cmd", "/c", shims[0]]
    exe = shutil.which("code")
    if exe and not exe.lower().endswith((".cmd", ".bat")):
        return [exe]
    for env_key, sub in (("LOCALAPPDATA", r"Programs\Microsoft VS Code\Code.exe"),
                         ("ProgramFiles", r"Microsoft VS Code\Code.exe"),
                         ("ProgramFiles(x86)", r"Microsoft VS Code\Code.exe")):
        cand = os.path.join(os.environ.get(env_key, ""), sub)
        if cand and os.path.isfile(cand):
            return [cand]
    return None


def _open_target(path, how) -> str:
    """Открывает проект: проводник / VS Code / терминал. Без shell-инъекций."""
    if how == "code":
        cmd = _code_launcher()
        if not cmd:
            raise OSError("VS Code не найден: нет 'code' в PATH и стандартных путей установки")
        subprocess.Popen(cmd + [path], shell=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "VS Code"
    if how in ("terminal", "cmd", "shell"):
        if sys.platform == "win32":
            subprocess.Popen(["cmd.exe", "/k", "cd", "/d", path], cwd=path,
                             creationflags=subprocess.CREATE_NEW_CONSOLE, shell=False)
            return "cmd.exe"
        subprocess.Popen(["x-terminal-emulator"], cwd=path, shell=False)
        return "terminal"
    if sys.platform == "win32":
        os.startfile(path)                               # noqa: S606 — путь проверен _within
        return "explorer"
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, path], shell=False)
    return opener


def serve(root=None, port=17373, open_browser=True):
    """Поднимает сервер и (опционально) открывает браузер. Блокирует поток."""
    root = norm_root(config.resolve_root(root))
    if not os.path.isdir(root):
        raise SystemExit(f"butler: папка не найдена: {root}")
    config.remember_root(root)
    httpd = ButlerHTTPServer(("127.0.0.1", port), ButlerHandler)
    httpd.butler_root = root
    url = f"http://127.0.0.1:{port}/"

    def startup_scan():
        save_projects(scan(root), root)
        write_feed(config.FEED_PATH, build_feed(root, list_projects(root)))

    httpd.butler_scan.start(root, startup_scan)     # через тот же ScanState: без гонок с ручным сканом
    print(f"Project Butler UI: {url}\nкорень: {root}\nфид: {config.FEED_PATH}\nCtrl+C — стоп.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлено.")
    finally:
        httpd.server_close()
    return 0
