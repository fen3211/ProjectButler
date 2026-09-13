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
    size_top INTEGER,
    has_readme INTEGER,
    has_env INTEGER,
    scanned_at REAL
)
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(SCHEMA)
    return conn


def save_projects(projects, root):
    conn = _connect()
    try:
        conn.execute("DELETE FROM projects WHERE root = ?", (root,))
        now = time.time()
        conn.executemany(
            "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(p.path, root, p.name, json.dumps(p.stacks, ensure_ascii=False),
              json.dumps(p.facts, ensure_ascii=False), p.mtime, p.size_top,
              int(p.has_readme), int(p.has_env), now) for p in projects],
        )
        conn.commit()
    finally:
        conn.close()


def list_projects(root=None):
    conn = _connect()
    try:
        q = ("SELECT path,root,name,stacks,facts,mtime,size_top,has_readme,has_env"
             " FROM projects")
        args = ()
        if root:
            q += " WHERE root = ?"
            args = (root,)
        rows = conn.execute(q + " ORDER BY name", args).fetchall()
    finally:
        conn.close()
    return [
        {"path": r[0], "root": r[1], "name": r[2],
         "stacks": json.loads(r[3]), "facts": json.loads(r[4]),
         "mtime": r[5], "size_top": r[6],
         "has_readme": bool(r[7]), "has_env": bool(r[8])}
        for r in rows
    ]
