"""MCP-сервер (stdio, JSON-RPC 2.0) на чистой стандартной библиотеке.

MCP по stdio — это построчный JSON-RPC, поэтому SDK тут не нужен: отдаём восемь
инструментов поверх собственной базы.

Поддержка: initialize / notifications/initialized / ping / tools/list / tools/call.
"""
import json
import sys
import traceback

from . import config
from .health import evaluate, primary_stack
from .index import build_feed, format_report, node as galaxy_node, summarize
from .scanner import scan
from .store import get_project, list_projects, norm_root, save_projects

SERVER_NAME = "project-butler"
SERVER_VERSION = "0.2.0"

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2025-06-18"

PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

ROOT_SCHEMA = {"type": "string", "description": "Папка с проектами (по умолчанию — из конфига)"}
LIMIT_SCHEMA = {"type": "integer", "description": "Лимит выдачи (по умолчанию 50)"}

TOOLS = [
    {
        "name": "butler_status",
        "description": "Сводка по папке проектов: сколько живых, сколько сгнило, средний health-score, TODO.",
        "inputSchema": {"type": "object", "properties": {
            "root": ROOT_SCHEMA,
            "rescan": {"type": "boolean", "description": "Пересканировать диск перед выдачей"}}},
    },
    {
        "name": "butler_list_projects",
        "description": "Список проектов с фильтрами по стеку, статусу и health-score.",
        "inputSchema": {"type": "object", "properties": {
            "root": ROOT_SCHEMA,
            "stack": {"type": "string", "description": "python / node / csharp / go / docker / js / git"},
            "status": {"type": "string", "description": "alive / abandoned / broken / unknown"},
            "min_score": {"type": "integer"},
            "max_score": {"type": "integer"},
            "limit": LIMIT_SCHEMA}},
    },
    {
        "name": "butler_project",
        "description": "Карточка проекта: стек, health с причинами, TODO, зависимости, чтение env.",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Имя или путь проекта"},
            "root": ROOT_SCHEMA}, "required": ["name"]},
    },
    {
        "name": "butler_dead_projects",
        "description": "Проекты, которые сгнили: заброшенные, сломанные, пустые — с причинами.",
        "inputSchema": {"type": "object", "properties": {"root": ROOT_SCHEMA}},
    },
    {
        "name": "butler_todos",
        "description": "TODO/FIXME/HACK по всем проектам с файлом и строкой.",
        "inputSchema": {"type": "object", "properties": {
            "root": ROOT_SCHEMA,
            "tag": {"type": "string", "description": "TODO / FIXME / HACK / XXX / BUG"},
            "project": {"type": "string"},
            "limit": LIMIT_SCHEMA}},
    },
    {
        "name": "butler_search",
        "description": "Поиск по имени проекта, README, зависимостям и тексту TODO.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "root": ROOT_SCHEMA}, "required": ["query"]},
    },
    {
        "name": "butler_scan",
        "description": "Пересканировать папку проектов и обновить базу.",
        "inputSchema": {"type": "object", "properties": {"root": ROOT_SCHEMA}},
    },
    {
        "name": "butler_galaxy",
        "description": "Фид «галактика проектов»: узлы с координатами, здоровьем и метриками.",
        "inputSchema": {"type": "object", "properties": {"root": ROOT_SCHEMA}},
    },
]


def _records(root=None, rescan=False):
    """Записи проектов: свежий скан по требованию, иначе — из базы (с автосканом пустой базы)."""
    root = norm_root(config.resolve_root(root))
    records = list_projects(root)
    fresh = False
    if rescan or not records:
        save_projects(scan(root), root)
        config.remember_root(root)
        records = list_projects(root)
        fresh = True
    return root, records, fresh


def _short(rec) -> dict:
    health = rec.get("health") or evaluate(rec)
    return {
        "name": rec["name"],
        "path": rec["path"],
        "stack": primary_stack(rec),
        "stacks": rec.get("stacks", []),
        "score": health.get("score", 0),
        "status": health.get("status", "unknown"),
        "idle_days": health.get("idle_days", 0),
        "todos": rec.get("todo_count", 0),
        "why": health.get("why", []),
    }


def _all_todos(records):
    items = []
    for rec in records:
        for item in (rec.get("facts") or {}).get("todos", []) or []:
            items.append({**item, "project": rec["name"], "path": rec["path"]})
    return items


def tool_status(args):
    root, records, fresh = _records(args.get("root"), bool(args.get("rescan")))
    nodes = [galaxy_node(r, root) for r in records]
    totals = summarize(nodes)
    lines = [
        f"Папка: {root}",
        f"Проектов: {totals['projects']} (источник: {'свежий скан' if fresh else 'база'})",
        f"Средний score: {totals['avg_score']}",
        f"TODO всего: {totals['todos']}",
        f"Живых: {totals['by_status'].get('alive', 0)}",
        f"Требуют внимания: {len(totals['dead'])}",
    ]
    if totals["dead"]:
        lines.append("Мертвецы: " + ", ".join(totals["dead"][:15]))
    lines += ["", format_report(records)]
    return "\n".join(lines)


def tool_list(args):
    root, records, _ = _records(args.get("root"))
    stack = (args.get("stack") or "").lower()
    status = (args.get("status") or "").lower()
    lo, hi = args.get("min_score"), args.get("max_score")
    limit = int(args.get("limit") or 50)
    out = []
    for rec in records:
        short = _short(rec)
        if stack and stack not in short["stacks"]:
            continue
        if status and short["status"] != status:
            continue
        if lo is not None and short["score"] < int(lo):
            continue
        if hi is not None and short["score"] > int(hi):
            continue
        out.append(short)
    out.sort(key=lambda s: s["score"])
    return json.dumps({"root": root, "count": len(out), "projects": out[:limit]},
                      ensure_ascii=False, indent=1)


def tool_project(args):
    root = norm_root(config.resolve_root(args.get("root")))
    rec = get_project(args["name"], root)
    if not rec:
        return f"Проект '{args['name']}' не найден в {root}. Начни с butler_list_projects."
    facts = rec.get("facts") or {}
    card = {
        "name": rec["name"],
        "path": rec["path"],
        "stacks": rec.get("stacks", []),
        "branch": facts.get("branch", "-"),
        "entry": facts.get("entry", ""),
        "markers": facts.get("markers", []),
        "health": rec.get("health") or evaluate(rec),
        "todos": (facts.get("todos") or [])[:20],
        "todo_count": rec.get("todo_count", 0),
        "env_reads": (facts.get("env_usage") or [])[:5],
        "dependencies": (facts.get("deps") or [])[:40],
        "deps_count": facts.get("deps_count", 0),
    }
    return json.dumps(card, ensure_ascii=False, indent=1)


def tool_dead(args):
    root, records, _ = _records(args.get("root"))
    dead = [_short(r) for r in records if _short(r)["status"] in ("abandoned", "broken", "unknown")]
    dead.sort(key=lambda s: (0 if s["status"] == "broken" else 1 if s["status"] == "abandoned" else 2,
                             s["score"]))
    if not dead:
        return f"В {root} некрополя нет — все проекты живые."
    lines = [f"Некрополь {root}: {len(dead)} шт.", ""]
    for d in dead:
        lines.append(f"- {d['name']} [{d['status']}, score {d['score']}, простой {d['idle_days']}d, "
                     f"TODO {d['todos']}] {d['why'][0] if d['why'] else ''}")
        lines.append(f"    {d['path']}")
    return "\n".join(lines)


def tool_todos(args):
    root, records, _ = _records(args.get("root"))
    tag = (args.get("tag") or "").upper() or None
    project = args.get("project")
    limit = int(args.get("limit") or 60)
    items = _all_todos(records)
    if tag:
        items = [i for i in items if i.get("tag", "").upper() == tag]
    if project:
        items = [i for i in items if project.lower() in i["project"].lower()]
    if not items:
        return "TODO-маркеров не найдено (или база устарела — вызови butler_scan)."
    lines = [f"TODO: {len(items)} шт. в {root}", ""]
    for i in items[:limit]:
        lines.append(f"- [{i.get('tag')}] {i['project']} :: {i.get('file')}:{i.get('line')} — {i.get('text')}")
    if len(items) > limit:
        lines.append(f"... и ещё {len(items) - limit}")
    return "\n".join(lines)


def tool_search(args):
    root, records, _ = _records(args.get("root"))
    needle = args["query"].lower()
    hits = []
    for rec in records:
        facts = rec.get("facts") or {}
        blob = " ".join([
            rec["name"], rec["path"], " ".join(rec.get("stacks", [])),
            " ".join(facts.get("markers", []) or []),
            " ".join(facts.get("deps", []) or []),
            " ".join(i.get("text", "") for i in (facts.get("todos") or [])),
        ]).lower()
        if needle in " ".join([rec["name"].lower(), rec["path"].lower()]):
            hits.append((rec, "имя/путь"))
        elif needle in blob:
            hits.append((rec, "README/зависимости/TODO"))
    if not hits:
        return f"По '{args['query']}' ничего не найдено в {root}."
    lines = [f"Найдено {len(hits)}:", ""]
    for rec, where in hits:
        short = _short(rec)
        lines.append(f"- {short['name']} [{short['stack']}, {short['status']}, score {short['score']}] "
                     f"— совпадение: {where}")
        lines.append(f"    {short['path']}")
    return "\n".join(lines)


def tool_scan(args):
    root, records, _ = _records(args.get("root"), rescan=True)
    nodes = [galaxy_node(r, root) for r in records]
    totals = summarize(nodes)
    return (f"Пересканировано: {root}\nПроектов: {totals['projects']}\n"
            f"Живых: {totals['by_status'].get('alive', 0)}, требуют внимания: {len(totals['dead'])}\n"
            f"Средний score: {totals['avg_score']}, TODO: {totals['todos']}")


def tool_galaxy(args):
    root, records, _ = _records(args.get("root"))
    return json.dumps(build_feed(root, records), ensure_ascii=False, indent=1)


HANDLERS = {
    "butler_status": tool_status,
    "butler_list_projects": tool_list,
    "butler_project": tool_project,
    "butler_dead_projects": tool_dead,
    "butler_todos": tool_todos,
    "butler_search": tool_search,
    "butler_scan": tool_scan,
    "butler_galaxy": tool_galaxy,
}


def call_tool(name, arguments):
    """Вызов инструмента: (текст, is_error)."""
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Неизвестный инструмент: {name}. Доступны: {', '.join(sorted(HANDLERS))}", True
    try:
        return str(handler(arguments or {})), False
    except Exception:                                   # noqa: BLE001 — клиенту нужен текст, не стектрейс
        return f"Ошибка в {name}: {traceback.format_exc(limit=3)}", True


def handle_request(req):
    """Обрабатывает один JSON-RPC запрос. None — если это нотификация (ответ не нужен)."""
    if not isinstance(req, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": INVALID_PARAMS, "message": "Запрос должен быть объектом"}}
    rid = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}
    is_notification = rid is None and method and method.startswith("notifications/")

    def ok(result):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid, "result": result}

    def fail(code, message):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid,
                                             "error": {"code": code, "message": message}}

    if method == "initialize":
        wanted = params.get("protocolVersion")
        protocol = wanted if wanted in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL
        return ok({
            "protocolVersion": protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": ("Project Butler: инвентаризация локальной папки с проектами. "
                             "butler_status — общая картина, butler_dead_projects — что сгнило, "
                             "butler_project — карточка проекта, butler_todos — хвосты, "
                             "butler_galaxy — фид для визуала. Всё локально, ничего не уходит в сеть."),
        })
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        if not name:
            return fail(INVALID_PARAMS, "Не указан name инструмента")
        text, is_error = call_tool(name, params.get("arguments"))
        return ok({"content": [{"type": "text", "text": text}], "isError": is_error})
    return fail(METHOD_NOT_FOUND, f"Метод не поддерживается: {method}")


def serve(in_stream=None, out_stream=None, root=None):
    """Цикл stdio: построчный JSON-RPC, ответ — построчно, UTF-8."""
    in_stream = in_stream if in_stream is not None else sys.stdin.buffer
    out_stream = out_stream if out_stream is not None else sys.stdout.buffer
    if root:
        config.remember_root(config.resolve_root(root))
    while True:
        try:
            line = in_stream.readline()
        except (KeyboardInterrupt, OSError):
            break
        if not line:
            break                                  # закрытый stdin = клиент ушёл
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": PARSE_ERROR, "message": "Невалидный JSON"}}
        else:
            response = handle_request(request)
        if response is None:
            continue
        payload = json.dumps(response, ensure_ascii=False, default=str)
        out_stream.write(payload.encode("utf-8") + b"\n")
        out_stream.flush()
    return 0


def main(root=None):
    return serve(root=root)
