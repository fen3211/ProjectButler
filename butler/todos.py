"""Работа с TODO-маркерами: фильтры, группировка, текстовый вывод."""


def filter_todos(items, tag=None, project=None):
    """Фильтр по тегу (TODO/FIXME/...) и/или имени проекта."""
    tag = tag.upper() if tag else None
    out = []
    for it in items or []:
        if tag and it.get("tag", "").upper() != tag:
            continue
        if project and project.lower() not in (it.get("project") or "").lower():
            continue
        out.append(it)
    return out


def count_by_tag(items):
    counts = {}
    for it in items or []:
        tag = it.get("tag", "?")
        counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def format_todos(items, limit=40):
    """Печатаемая таблица: project | file:line | tag | text."""
    items = list(items or [])
    if not items:
        return "TODO-маркеров не найдено."
    rows = []
    for it in items[:limit]:
        loc = f"{it.get('file', '?')}:{it.get('line', '?')}"
        rows.append((it.get("project", "?"), loc, it.get("tag", "?"), it.get("text", "")))
    head = ("PROJECT", "WHERE", "TAG", "TEXT")
    widths = [len(h) for h in head]
    for r in rows:
        widths = [max(w, len(str(c))) for w, c in zip(widths, r)]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    out = [fmt.format(*head), "-" * (sum(widths) + 2 * (len(widths) - 1))]
    out += [fmt.format(*r) for r in rows]
    if len(items) > limit:
        out.append(f"... и ещё {len(items) - limit} (лимит вывода {limit})")
    return "\n".join(out)
