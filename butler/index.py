"""Фид galaxy.json + текстовые сводки. Раскладка детерминированная: путь -> точка."""
import hashlib
import json
import math
import os
import time

from . import health as H

FEED_VERSION = 2

# Центры кластеров по стекам (условные единицы, визуал сам решает масштаб)
CLUSTERS = {
    "python": (0.0, 0.0, 0.0),
    "node": (2.6, -0.9, 0.6),
    "csharp": (-2.7, -1.1, -0.5),
    "go": (3.1, 1.5, -0.4),
    "docker": (-1.7, 2.4, 0.5),
    "js": (-3.5, 0.8, 0.0),
    "git": (0.6, 3.3, -0.6),
    "unknown": (0.0, -3.2, 0.9),
}

STATUS_LABEL = {
    "alive": "живой",
    "abandoned": "заброшен",
    "broken": "сломан",
    "unknown": "пусто",
}


def _val(rec, key, default=None):
    if isinstance(rec, dict):
        return rec.get(key, default)
    return getattr(rec, key, default)


def slug(name: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in name)
    return "-".join(p for p in out.split("-") if p) or "project"


def layout(project_path: str, stack: str):
    """Детерминированная позиция: один и тот же путь всегда в одной точке галактики."""
    cx, cy, cz = CLUSTERS.get(stack, CLUSTERS["unknown"])
    h = int(hashlib.sha1(project_path.encode("utf-8")).hexdigest()[:8], 16)
    angle = (h % 3600) / 3600.0 * 2 * math.pi
    radius = 0.55 + ((h >> 12) % 1000) / 1000.0 * 1.55
    jitter_z = ((h >> 6) % 1000) / 1000.0 * 1.8 - 0.9
    return [
        round(cx + radius * math.cos(angle), 4),
        round(cy + radius * math.sin(angle), 4),
        round(cz + jitter_z, 4),
    ]


def _readme_tagline(rec) -> str:
    """Первая осмысленная строка README — для карточки в визуале."""
    facts = _val(rec, "facts", {}) or {}
    base = _val(rec, "path", "") or ""
    nested = facts.get("nested_root") if isinstance(facts, dict) else None
    folders = ([os.path.join(base, nested)] if nested else []) + [base]
    for folder in folders:
        for name in ("README.md", "readme.md", "README.MD", "README.rst", "README.txt"):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip().lstrip("#").strip()
                        if line and not line.startswith((">", "`", "!", "[", "|", "=", "-", "*")):
                            return line[:160]
            except OSError:
                continue
    return ""


def node(rec, root) -> dict:
    """Проект -> узел галактики."""
    facts = _val(rec, "facts", {}) or {}
    stacks = list(_val(rec, "stacks", []) or [])
    stack = H.primary_stack(rec)
    health = _val(rec, "health", {}) or {}
    if not health:
        health = H.evaluate(rec)
    path = _val(rec, "path", "")
    try:
        rel = os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        rel = _val(rec, "name", "")
    status = health.get("status", "unknown")
    return {
        "id": slug(_val(rec, "name", "")),
        "name": _val(rec, "name", ""),
        "path": path,
        "rel": rel,
        "stacks": stacks,
        "stack": stack,
        "score": health.get("score", 0),
        "status": status,
        "status_label": STATUS_LABEL.get(status, status),
        "idle_days": health.get("idle_days", H.days_idle(rec)),
        "why": (health.get("why") or [])[:3],
        "penalties": health.get("penalties", []),
        "bonuses": health.get("bonuses", []),
        "todos": _val(rec, "todo_count", 0) or 0,
        "size_top": _val(rec, "size_top", 0) or 0,
        "has_readme": bool(_val(rec, "has_readme", False)),
        "has_git": "git" in stacks,
        "branch": facts.get("branch", "-"),
        "deps": len(facts.get("deps", []) or []) or facts.get("deps_count", 0) or 0,
        "entry": facts.get("entry", ""),
        "tagline": _readme_tagline(rec),
        "pos": layout(path, stack),
    }


def summarize(nodes) -> dict:
    by_status, by_stack, todos, score_sum = {}, {}, 0, 0
    for n in nodes:
        by_status[n["status"]] = by_status.get(n["status"], 0) + 1
        by_stack[n["stack"]] = by_stack.get(n["stack"], 0) + 1
        todos += n["todos"]
        score_sum += n["score"]
    count = len(nodes)
    return {
        "projects": count,
        "avg_score": round(score_sum / count, 1) if count else 0,
        "todos": todos,
        "by_status": dict(sorted(by_status.items(), key=lambda kv: -kv[1])),
        "by_stack": dict(sorted(by_stack.items(), key=lambda kv: -kv[1])),
        "dead": sorted(n["name"] for n in nodes if n["status"] in ("broken", "abandoned", "unknown")),
        "healthy": sorted(n["name"] for n in nodes if n["status"] == "alive"),
    }


def build_feed(root, records) -> dict:
    """Собирает фид. records — записи store.list_projects или объекты Project."""
    nodes = [node(r, root) for r in records]
    return {
        "feed_version": FEED_VERSION,
        "generated_at": time.time(),
        "generated_at_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        "root": root,
        "clusters": {k: list(v) for k, v in CLUSTERS.items()},
        "totals": summarize(nodes),
        "projects": sorted(nodes, key=lambda n: (-n["score"], n["name"])),
    }


def write_feed(path, feed) -> None:
    """Атомарная запись: половина файла в браузере хуже, чем отсутствие файла."""
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(feed, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_feed(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def format_report(records) -> str:
    """Таблица «сначала сгнившее»: NAME STACK SCORE STATUS IDLE TD WHY."""
    recs = H.worst_first(records)
    if not recs:
        return "В базе пусто — сначала `python -m butler scan <папка>`."
    rows = []
    for r in recs:
        health = _val(r, "health", {}) or {}
        score = health.get("score", _val(r, "score", 0) or 0)
        status = health.get("status", _val(r, "status", "unknown")) or "unknown"
        idle = health.get("idle_days", _val(r, "idle_days", 0)) or 0
        why = (health.get("why") or _val(r, "why", []) or [""])[0]
        rows.append((str(_val(r, "name", "?")),
                     H.primary_stack(r),
                     str(score),
                     STATUS_LABEL.get(status, status),
                     f"{idle}d",
                     str(_val(r, "todo_count", 0) or 0),
                     str(why)))
    head = ("NAME", "STACK", "SCORE", "STATUS", "IDLE", "TD", "WHY")
    widths = [len(h) for h in head]
    for r in rows:
        widths = [max(w, len(c)) for w, c in zip(widths, r)]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    out = [fmt.format(*head), "-" * (sum(widths) + 2 * (len(widths) - 1))]
    out += [fmt.format(*r) for r in rows]

    totals = summarize([node(r, _val(r, "root", "") or "") for r in recs])
    out.append("")
    out.append(f"всего {totals['projects']}, средний score {totals['avg_score']}, "
               f"TODO {totals['todos']}, требуют внимания {len(totals['dead'])}")
    for status in ("alive", "abandoned", "broken", "unknown"):
        if status in totals["by_status"]:
            out.append(f"  {STATUS_LABEL[status]}: {totals['by_status'][status]}")
    return "\n".join(out)
