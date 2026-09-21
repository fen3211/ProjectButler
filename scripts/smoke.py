"""E2E-проверка локального API без браузера: поднимает сервер в потоке и дёргает маршруты.

Запуск: py -3.12 scripts/smoke.py ["D:\\Projects"]
Открытие папок подменено заглушкой — скрипт ничего не запускает в системе.
"""
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

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

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), webserver.ButlerHandler)
    httpd.butler_root = root
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"сервер: http://127.0.0.1:{PORT}  корень: {root}\n")

    status, body = request("/api/health")
    check("GET /api/health = 200", status == 200, body[:80])

    status, body = request("/")
    check("GET / отдаёт визуал", status == 200 and "галактика" in body,
          f"{len(body)} байт")

    status, body = request("/ui/galaxy.js")
    check("GET /ui/galaxy.js = 200", status == 200, f"{len(body)} байт")

    status, body = request("/galaxy.json")
    check("GET /galaxy.json = 200", status == 200)
    feed = json.loads(body) if status == 200 else {}
    check("фид содержит проекты", bool(feed.get("projects")), f"{len(feed.get('projects', []))} шт.")

    status, body = request("/api/scan", "POST", {})
    check("POST /api/scan = 200", status == 200, body[:120])
    scanned = json.loads(body) if status == 200 else {}
    check("скан нашёл проекты", scanned.get("totals", {}).get("projects", 0) > 0,
          f"{scanned.get('totals', {}).get('projects', 0)} проектов")

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
