"""E2E-проверка локального API без браузера: поднимает сервер в потоке и дёргает маршруты.

Запуск: py -3.12 scripts/smoke.py ["D:\\Projects"]
Открытие папок подменено заглушкой — скрипт ничего не запускает в системе.
"""
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from butler import webserver                              # noqa: E402
from butler.store import norm_root                        # noqa: E402

PORT = 17499
FAILS = []


def check(name, condition, detail=""):
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILS.append(name)


def request(path, method="GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main():
    root = norm_root(sys.argv[1] if len(sys.argv) > 1 else r"D:\Projects")
    opened = []
    webserver._open_target = lambda path, how: (opened.append((path, how)), "stub")[1]

    httpd = webserver.ButlerHTTPServer(("127.0.0.1", PORT), webserver.ButlerHandler)
    httpd.butler_root = root
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"сервер: http://127.0.0.1:{PORT}  корень: {root}\n")

    status, body = request("/api/health")
    check("GET /api/health = 200", status == 200, body[:80])

    status, body = request("/")
    check("GET / отдаёт визуал", status == 200 and "галактика" in body,
          f"{len(body)} байт")

    import re
    src = re.search(r'src="([^"]+)"', body)
    check("в HTML есть <script src>", bool(src))
    if src:
        status_js, _ = request(src.group(1))
        check("script src из HTML реально отдаётся", status_js == 200, src.group(1))

    status, body = request("/ui/galaxy.js")
    check("GET /ui/galaxy.js = 200", status == 200, f"{len(body)} байт")

    status, body = request("/galaxy.json")
    check("GET /galaxy.json = 200", status == 200)
    feed = json.loads(body) if status == 200 else {}
    check("фид содержит проекты", bool(feed.get("projects")), f"{len(feed.get('projects', []))} шт.")

    import time as _time

    def wait_scan(seconds=180):
        deadline = _time.time() + seconds
        while _time.time() < deadline:
            status, body = request("/api/scan-status")
            data = json.loads(body) if status == 200 else {}
            if not data.get("running"):
                return data
            _time.sleep(0.3)
        return {"running": True, "error": "таймаут ожидания скана"}

    status, body = request("/api/scan", "POST", {})
    check("POST /api/scan отвечает мгновенно и уходит в фон", status == 200, body[:120])
    scanned = json.loads(body) if status == 200 else {}
    check("POST /api/scan = фоновый режим", scanned.get("scanning") is True, body[:80])
    finished = wait_scan()
    check("фоновый скан завершился без ошибок", not finished.get("running") and not finished.get("error"),
          str(finished.get("error") or "ok"))
    status, body = request("/galaxy.json")
    scanned = json.loads(body) if status == 200 else {}
    check("скан нашёл проекты", scanned.get("totals", {}).get("projects", 0) > 0,
          f"{scanned.get('totals', {}).get('projects', 0)} проектов")

    status, body = request("/api/roots")
    check("GET /api/roots = 200", status == 200, body[:90])

    status, body = request("/api/digest")
    data = json.loads(body) if status == 200 else {}
    check("GET /api/digest = диф и цифры", status == 200 and "diff" in data and
          "junk_bytes" in data and "projects" in data,
          f"{data.get('projects')} проектов, diff.scans={data.get('diff', {}).get('scans')}")

    status, body = request("/api/feed-version")
    data = json.loads(body) if status == 200 else {}
    check("GET /api/feed-version = mtime фида", status == 200 and data.get("mtime", 0) > 0,
          str(data.get("mtime")))

    status, body = request("/api/settings")
    data = json.loads(body) if status == 200 else {}
    check("GET /api/settings = дефолты", status == 200 and "theme" in data and "lang" in data,
          str(data.get("theme")))
    status, body = request("/api/settings", "POST", {"theme": "deepspace", "lang": "en", "hack": 1})
    data = json.loads(body) if status == 200 else {}
    check("POST /api/settings сохраняет и валидирует", status == 200 and
          data.get("theme") == "deepspace" and data.get("lang") == "en" and "hack" not in data,
          str(data.get("theme")))
    request("/api/settings", "POST", {"theme": "darkmatter", "lang": "ru"})

    status, body = request("/api/gh/status")
    data = json.loads(body) if status == 200 else {}
    check("GET /api/gh/status без токена = не авторизован", status == 200 and
          data.get("authed") is False, str(data.get("authed")))

    status, body = request("/api/gh/repo?path=" + quote(r"C:\Windows"))
    check("GET /api/gh/repo вне корня = 403", status == 403, body[:80])

    status, body = request("/api/wrapped")
    data = json.loads(body) if status == 200 else {}
    check("GET /api/wrapped = отчёт миссии", status == 200 and "scans" in data and
          "period_days" in data and "best" in data and "todos_first" in data,
          f"сканов: {data.get('scans')}, дней: {data.get('period_days')}")

    status, body = request("/api/settings", "POST", {"watch": True})
    data = json.loads(body) if status == 200 else {}
    check("POST /api/settings watch-тумблер", status == 200 and data.get("watch") is True,
          str(data.get("watch")))
    request("/api/settings", "POST", {"watch": False})

    status, body = request("/api/search?q=" + quote("Проект"))
    data = json.loads(body) if status == 200 else {}
    check("GET /api/search ищет по содержимому", status == 200 and isinstance(data.get("results"), list),
          f"{len(data.get('results', []))} совпадений")

    status, body = request("/api/tags", "POST", {"path": r"C:\Windows", "tags": ["x"]})
    check("POST /api/tags вне корня = 403", status == 403, body[:80])

    status, body = request("/api/browse")
    data = json.loads(body) if status == 200 else {}
    check("GET /api/browse без пути = диски", status == 200 and isinstance(data.get("drives"), list),
          ", ".join(data.get("drives", [])[:8]))

    status, body = request("/api/browse?path=" + quote("D:/"))
    data = json.loads(body) if status == 200 else {}
    check("GET /api/browse D:/ = подпапки", status == 200 and isinstance(data.get("dirs"), list)
          and not data.get("error"), f"{len(data.get('dirs', []))} папок")

    status, body = request("/api/browse?path=" + quote("X:/No/Such/Dir42"))
    check("GET /api/browse битый путь = 400", status == 400, body[:80])

    status, body = request("/api/root", "POST", {"root": ""})
    check("POST /api/root пустой путь = 400", status == 400, body[:80])

    status, body = request("/api/root", "POST", {"root": r"C:\No\Such\Folder\Ever42"})
    check("POST /api/root нет такой папки = 400", status == 400, body[:80])

    # переключение на временную папку с одним мини-проектом, потом обратно
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "Mini"
        proj.mkdir()
        (proj / "README.md").write_text("# Mini\n", encoding="utf-8")
        (proj / "requirements.txt").write_text("requests\n", encoding="utf-8")
        (proj / "bot.py").write_text(
            "import os\nTOKEN = os.getenv('BOT_TOKEN')\n"
            "# TODO заложить телеметрию\nprint('mini')\n", encoding="utf-8")
        status, body = request("/api/root", "POST", {"root": tmp})
        switched = json.loads(body) if status == 200 else {}
        check("POST /api/root отвечает мгновенно и уходит в фон", status == 200 and
              switched.get("scanning") is True, body[:80])
        finished = wait_scan()
        check("фоновый скан временной папки завершился без ошибок", not finished.get("running")
              and not finished.get("error"), str(finished.get("error") or "ok"))
        status, body = request("/galaxy.json")
        feed2 = json.loads(body) if status == 200 else {}
        mini = [p for p in feed2.get("projects", []) if p.get("name") == "Mini"]
        check("после фонового скана фид переключился на новую папку", status == 200 and len(mini) == 1,
              f"проектов: {len(feed2.get('projects', []))}")

        status, body = request("/api/tags", "POST", {"path": str(proj), "tags": ["smoke", " тест ", "smoke"]})
        data = json.loads(body) if status == 200 else {}
        check("POST /api/tags пишет и нормализует", status == 200 and data.get("tags") == ["smoke", "тест"],
              str(data.get("tags")))
        status, body = request("/api/note", "POST", {"path": str(proj), "note": "  привет  "})
        data = json.loads(body) if status == 200 else {}
        check("POST /api/note пишет заметку", status == 200 and data.get("note") == "привет",
              str(data.get("note")))
        status, body = request("/api/resurrect", "POST", {"path": str(proj)})
        data = json.loads(body) if status == 200 else {}
        check("POST /api/resurrect без confirm = план", status == 200 and
              isinstance(data.get("plan", {}).get("steps"), list) and data["plan"]["steps"],
              str(data.get("plan", {}).get("steps"))[:90])

        status, body = request("/api/search?q=" + quote("телеметрию"))
        data = json.loads(body) if status == 200 else {}
        hit = next((r for r in data.get("results", []) if r.get("name") == "Mini"), None)
        check("GET /api/search находит по TODO-тексту", status == 200 and hit is not None
              and "TODO" in (hit.get("where") or ""), str(hit))

        status, body = request("/api/readme", "POST", {"path": str(proj)})
        data = json.loads(body) if status == 200 else {}
        check("POST /api/readme не трогает рукописный", status == 200 and data.get("written") is False,
              str(data.get("reason")))

        status, body = request("/api/doctor", "POST", {"path": str(proj)})
        data = json.loads(body) if status == 200 else {}
        names = [c.get("check") for c in data.get("checks", [])]
        check("POST /api/doctor даёт проверки окружения", status == 200 and len(names) >= 2,
              ", ".join(names[:4]))

        status, body = request("/api/gitpulse?path=" + quote(str(proj)))
        data = json.loads(body) if status == 200 else {}
        check("GET /api/gitpulse = 30 дней пульса", status == 200 and
              (len(data.get("days", [])) == 30 or data.get("total", -1) == 0),
              f"дней: {len(data.get('days', []))}, коммитов: {data.get('total')}")

    status, body = request("/api/root", "POST", {"root": root})
    check("переключение обратно на исходный корень", status == 200, root)
    finished = wait_scan()
    check("обратный фоновый скан завершился", not finished.get("running") and not finished.get("error"),
          str(finished.get("error") or "ok"))

    status, body = request("/api/open", "POST", {"path": r"C:\Windows", "with": "explorer"})
    check("POST /api/open вне корня = 403", status == 403, body[:80])

    status, body = request("/api/open", "POST", {"path": "", "with": "explorer"})
    check("POST /api/open с пустым путём = 403", status == 403, body[:80])

    inside = None
    for node in feed.get("projects", []):
        inside = node["path"]
        break
    status, body = request("/api/open", "POST", {"path": inside, "with": "explorer"})
    check("POST /api/open внутри корня = 200 (заглушка)", status == 200 and opened,
          f"{inside}")

    status, body = request("/api/nope")
    check("неизвестный маршрут = 404", status == 404, body[:80])

    httpd.shutdown()
    print()
    if FAILS:
        print(f"ПРОВАЛЕНО: {len(FAILS)} — {', '.join(FAILS)}")
        return 1
    print("SMOKE OK — все проверки пройдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
