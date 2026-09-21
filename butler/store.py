"""SQLite-хранилище результатов: ~/.project-butler/butler.db. Только стандартная библиотека."""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path.home() / ".project-butler" / "butler.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    path TEXT PRIMARY KEY,
    root TEXT,
    name TEXT,
    stacks TEXT,
    facts TEXT,
    mtime REAL,
    activity REAL,
    size_top INTEGER,
    has_readme INTEGER,
    has_env INTEGER,
    todo_count INTEGER,
    health TEXT,
    scanned_at REAL
)
"""

# Колонки, которые досыпаются в старую базу через ALTER TABLE (миграция без потери данных)
MIGRATIONS = {
    "activity": "ALTER TABLE projects ADD COLUMN activity REAL",
    "todo_count": "ALTER TABLE projects ADD COLUMN todo_count INTEGER",
    "health": "ALTER TABLE projects ADD COLUMN health TEXT",
}

FIELDS = ("path", "root", "name", "stacks", "facts", "mtime", "activity", "size_top",
          "has_readme", "has_env", "todo_count", "health")


def norm_root(root) -> str:
    """Канонический вид корня, чтобы 'D:\\Projects' и 'D:\\Projects\\' не двоили строки."""
    try:
        return str(Path(root).resolve())
    except OSError:
        return str(root)


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row          # доступ по именам колонок: ALTER TABLE не ломает чтение
    conn.execute(SCHEMA)
    have = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    for col, ddl in MIGRATIONS.items():
        if col not in have:
            conn.execute(ddl)
    return conn


def _val(rec, key, default=None):
    if isinstance(rec, dict):
        return rec.get(key, default)
    return getattr(rec, key, default)


def save_projects(projects, root):
    conn = _connect()
    try:
        conn.execute("DELETE FROM projects WHERE root = ?", (root,))
        now = time.time()
        # Колонки перечисляем ЯВНО: ALTER TABLE меняет физический порядок, позиционный INSERT — ловушка
        placeholders = ",".join("?" * (len(FIELDS) + 1))
        conn.executemany(
            "INSERT INTO projects (" + ",".join(FIELDS) + ",scanned_at) VALUES (" + placeholders + ")",
            [(
                _val(p, "path"), root, _val(p, "name"),
                json.dumps(_val(p, "stacks", []) or [], ensure_ascii=False),
                json.dumps(_val(p, "facts", {}) or {}, ensure_ascii=False),
                _val(p, "mtime", 0.0) or 0.0,
                _val(p, "activity", 0.0) or 0.0,
                _val(p, "size_top", 0) or 0,
                int(bool(_val(p, "has_readme", False))),
                int(bool(_val(p, "has_env", False))),
                _val(p, "todo_count", 0) or 0,
                json.dumps(_val(p, "health", {}) or {}, ensure_ascii=False),
                now,
            ) for p in projects],
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(r) -> dict:
    """Читает строку по именам колонок, поэтому миграции ALTER TABLE безопасны."""
    def get(key, default=None):
        try:
            value = r[key]
        except (IndexError, KeyError):
            return default
        return default if value is None else value

    raw_health = get("health", "")
    health = raw_health if isinstance(raw_health, dict) else {}
    if isinstance(raw_health, str) and raw_health.strip():
        try:
            health = json.loads(raw_health)
        except ValueError:
            health = {}
    if not isinstance(health, dict):
        health = {}

    def load_json(key, fallback):
        raw = get(key, "")
        if isinstance(raw, (list, dict)):
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return fallback

    return {
        "path": get("path", ""),
        "root": get("root", ""),
        "name": get("name", ""),
        "stacks": load_json("stacks", []),
        "facts": load_json("facts", {}),
        "mtime": get("mtime", 0.0) or 0.0,
        "activity": get("activity", 0.0) or 0.0,
        "size_top": get("size_top", 0) or 0,
        "has_readme": bool(get("has_readme", 0)),
        "has_env": bool(get("has_env", 0)),
        "todo_count": get("todo_count", 0) or 0,
        "health": health,
        # дублируем наружу — чтобы вызывающему коду не лазить в словарь
        "score": health.get("score", 0),
        "status": health.get("status", "unknown"),
        "why": health.get("why", []),
    }


def list_projects(root=None):
    conn = _connect()
    try:
        q = "SELECT " + ",".join(FIELDS) + " FROM projects"
        args = ()
        if root:
            q += " WHERE root = ?"
            args = (root,)
        rows = conn.execute(q + " ORDER BY name", args).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(r) for r in rows]


def get_project(name_or_path, root=None):
    """Поиск проекта: точное имя/путь, затем подстрока по имени и пути."""
    needle = str(name_or_path).strip().lower()
    records = list_projects(root)
    for rec in records:
        if rec["name"].lower() == needle or rec["path"].lower() == needle:
            return rec
    for rec in records:
        if needle in rec["name"].lower() or needle in rec["path"].lower().replace("\\", "/"):
            return rec
    return None
