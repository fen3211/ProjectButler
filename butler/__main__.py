"""CLI: python -m butler scan <папка> | list [--root <папка>]."""
import argparse
from datetime import datetime

from .scanner import scan
from .store import DB_PATH, list_projects, save_projects


def _table(projects) -> str:
    rows = []
    for p in projects:
        stacks = ",".join(p.stacks) if p.stacks else "-"
        branch = p.facts.get("branch", "-")
        upd = datetime.fromtimestamp(p.mtime).strftime("%Y-%m-%d") if p.mtime else "-"
        rows.append((p.name, stacks, branch,
                     "Y" if p.has_readme else ".",
                     "Y" if p.has_env else ".", upd))
    head = ("NAME", "STACKS", "BRANCH", "RM", "ENV", "UPDATED")
    widths = [len(h) for h in head]
    for r in rows:
        widths = [max(w, len(c)) for w, c in zip(widths, r)]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    out = [fmt.format(*head), "-" * (sum(widths) + 2 * (len(widths) - 1))]
    out += [fmt.format(*r) for r in rows]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(prog="butler", description="Project Butler — пилот по папке с проектами")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_scan = sub.add_parser("scan", help="сканировать папку и сохранить в базу")
    p_scan.add_argument("root", help=r"папка с проектами, напр. D:\Projects")
    p_list = sub.add_parser("list", help="показать проекты из базы")
    p_list.add_argument("--root", default=None)
    args = ap.parse_args()
    if args.cmd == "scan":
        projects = scan(args.root)
        save_projects(projects, args.root)
        print(_table(projects))
        print(f"\n{len(projects)} проектов -> {DB_PATH}")
    else:
        rows = list_projects(args.root)
        print(f"{len(rows)} проектов в базе ({DB_PATH}):")
        for r in rows:
            print(f"- {r['name']} [{','.join(r['stacks']) or '-'}] {r['path']}")


if __name__ == "__main__":
    main()
