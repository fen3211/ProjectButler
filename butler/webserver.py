"""Локальный сервер для визуала: статика ui/, фид и мини-API. Слушает только 127.0.0.1."""
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config
from .index import build_feed, read_feed, summarize, write_feed, node as galaxy_node
from .scanner import scan
from .store import list_projects, norm_root, save_projects

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
        if path == "/galaxy.json":
            feed = read_feed(config.FEED_PATH)
            return self._json(feed if feed is not None else self._rebuild_feed())
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
        return self._error(404, f"Нет такого маршрута: {path}")

    def do_POST(self):                                   # noqa: N802
        path = self.path.split("?", 1)[0]
        args = self._body()
        if path == "/api/scan":
            root = norm_root(args.get("root") or self.root)
            if not os.path.isdir(root):
                return self._error(400, f"Папка не найдена: {root}")
            save_projects(scan(root), root)
            config.remember_root(root)
            feed = build_feed(root, list_projects(root))
            write_feed(config.FEED_PATH, feed)
            return self._json({"ok": True, "root": root, "totals": feed["totals"]})
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
        return self._error(404, f"Нет такого маршрута: {path}")


def _open_target(path, how) -> str:
    """Открывает проект: проводник / VS Code / терминал. Без shell-инъекций."""
    if how == "code":
        subprocess.Popen(["code", path], shell=False,
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
    httpd = ThreadingHTTPServer(("127.0.0.1", port), ButlerHandler)
    httpd.butler_root = root
    url = f"http://127.0.0.1:{port}/"
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
