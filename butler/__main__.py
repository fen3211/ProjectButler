"""CLI: scan | list | report | todos | export | ui | mcp."""
import argparse
import sys
from pathlib import Path

from . import config
from .health import evaluate, primary_stack
from .index import build_feed, format_report, summarize, write_feed, node as galaxy_node
from .scanner import scan
from .store import DB_PATH, list_projects, norm_root, save_projects
from .todos import format_todos


def _root(args) -> str:
    return norm_root(config.resolve_root(getattr(args, "root", None)))


def _require(root) -> str:
    if not Path(root).is_dir():
        raise SystemExit(f"butler: папка не найдена: {root}")
    return root


def _rescan(root):
    """Скан + запись в базу + запоминание корня. Возвращает свежие записи."""
    projects = scan(root)
    save_projects(projects, root)
    config.remember_root(root)
    return list_projects(root)


def _all_todos(records):
    items = []
    for rec in records:
        for item in (rec.get("facts") or {}).get("todos", []) or []:
            items.append({**item, "project": rec["name"], "path": rec["path"]})
    return items


def cmd_scan(args):
    root = _require(_root(args))
    records = _rescan(root)
    print(format_report(records))
    print(f"\nбаза: {DB_PATH}")
    return 0


def cmd_list(args):
    root = _root(args)
    records = list_projects(root)
    if not records:
        print(f"В базе пусто для {root}. Запусти: python -m butler scan \"{root}\"")
        return 0
    stack = (args.stack or "").lower()
    status = (args.status or "").lower()
    shown = 0
    for rec in records:
        health = rec.get("health") or evaluate(rec)
        if stack and stack not in (rec.get("stacks") or []):
            continue
        if status and health.get("status") != status:
            continue
        print(f"{health.get('score', 0):>3}  {health.get('status', '?'):<9} "
              f"{primary_stack(rec):<7} {rec['name']:<22} {rec['path']}")
        shown += 1
        if shown >= args.limit:
            break
    print(f"\nпоказано {shown} из {len(records)}")
    return 0


def cmd_report(args):
    root = _require(_root(args))
    records = _rescan(root) if args.rescan else list_projects(root)
    if not records:
        records = _rescan(root)
    print(format_report(records))
    return 0


def cmd_todos(args):
    root = _root(args)
    records = list_projects(root)
    if not records:
        records = _rescan(root)
    items = _all_todos(records)
    if args.tag:
        items = [i for i in items if i.get("tag", "").upper() == args.tag.upper()]
    if args.project:
        items = [i for i in items if args.project.lower() in i["project"].lower()]
    print(format_todos(items, limit=args.limit))
    return 0


def cmd_export(args):
    root = _require(_root(args))
    records = list_projects(root) if args.no_scan else _rescan(root)
    feed = build_feed(root, records)
    out = Path(args.out) if args.out else config.FEED_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    write_feed(out, feed)
    totals = feed["totals"]
    print(f"фид: {out}")
    print(f"проектов {totals['projects']}, средний score {totals['avg_score']}, "
          f"TODO {totals['todos']}, требуют внимания {len(totals['dead'])}")
    for status, count in totals["by_status"].items():
        print(f"  {status}: {count}")
    return 0


def cmd_ui(args):
    from .webserver import serve
    _require(_root(args))
    return serve(root=args.root, port=args.port, open_browser=not args.no_browser)


def cmd_mcp(args):
    from . import mcp_server
    return mcp_server.main(root=args.root)


def _force_utf8():
    """Русская Windows-консоль по умолчанию в cp1251/cp866 — кириллица выходит кашей."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_parser():
    ap = argparse.ArgumentParser(prog="butler", description="Project Butler — пилот по папке с проектами")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="сканировать папку и сохранить в базу")
    p.add_argument("root", nargs="?", default=None, help=r"папка с проектами, напр. D:\Projects")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("list", help="проекты из базы (score / статус / стек)")
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--stack", default=None)
    p.add_argument("--status", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("report", help="таблица «сначала сгнившее»")
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--rescan", action="store_true", help="пересканировать перед отчётом")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("todos", help="TODO/FIXME по проектам")
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--tag", default=None)
    p.add_argument("--project", default=None)
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_todos)

    p = sub.add_parser("export", help="собрать фид galaxy.json для визуала")
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--no-scan", action="store_true", help="не пересканировать, взять базу")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("ui", help="поднять визуал на http://127.0.0.1:17373")
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--port", type=int, default=17373)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_ui)

    p = sub.add_parser("mcp", help="MCP-сервер по stdio (для Claude/Cline)")
    p.add_argument("root", nargs="?", default=None)
    p.set_defaults(func=cmd_mcp)
    return ap


def main(argv=None):
    _force_utf8()
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
