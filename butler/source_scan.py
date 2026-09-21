"""Один проход по исходникам проекта: TODO-маркеры, признаки чтения env, активность.

Только чтение, жёсткие лимиты, чтобы папка на 50k файлов не подвесила скан.
"""
import os
import re

# Каталоги, которые не являются «нашим» кодом
SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules", "site-packages",
    ".next", "out", "dist", "build", "target", "bin", "obj", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".idea", ".vscode", "coverage", ".tox", "vendor",
    "downloads", "output", "temp", ".gradle", ".cache", "packages", "models",
}

CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".cs", ".go", ".rs", ".java",
    ".php", ".rb", ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".lua", ".dart",
    ".sh", ".ps1", ".bat", ".cmd", ".vue", ".svelte", ".sql", ".yml", ".yaml",
    ".toml", ".cfg", ".ini", ".md", ".txt", ".env", ".env.example",
}

TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|BUG)\b[:：\s\-]*(.{0,160})")
ENV_PATTERNS = (
    (re.compile(r"os\.getenv\s*\("), "os.getenv"),
    (re.compile(r"os\.environ\s*[\[\(]"), "os.environ"),
    (re.compile(r"process\.env\.[A-Za-z_]"), "process.env"),
    (re.compile(r"Environment\.GetEnvironmentVariable"), "Environment.GetEnvironmentVariable"),
    (re.compile(r"getenv\s*\("), "getenv"),
)

MAX_FILES = 900
MAX_BYTES = 512 * 1024
MAX_TODOS = 300
MAX_ENV_USAGE = 8


def _read_text(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return None


def scan_sources(root) -> dict:
    """Обходит дерево root, возвращает todos / env_usage / счётчики / newest_mtime."""
    root = os.fspath(root)
    todos, env_usage = [], []
    code_files = 0
    files_seen = 0
    newest = 0.0
    test_files = 0

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if files_seen >= MAX_FILES:
                break
            files_seen += 1
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace("\\", "/")
            ext = os.path.splitext(name)[1].lower()
            if name.startswith(("test_", "spec_")) or name.endswith(
                    (".test.ts", ".test.tsx", ".test.js", ".spec.ts")):
                test_files += 1
            is_code = ext in CODE_EXT or name.startswith(".env")
            if is_code:
                code_files += 1
            try:
                stamp = os.stat(path).st_mtime
                if stamp > newest:
                    newest = stamp
            except OSError:
                pass
            if not is_code:
                continue
            if len(todos) >= MAX_TODOS and len(env_usage) >= MAX_ENV_USAGE:
                continue
            text = _read_text(path)
            if text is None:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if len(todos) < MAX_TODOS:
                    hit = TODO_RE.search(line)
                    if hit:
                        todos.append({
                            "file": rel, "line": lineno, "tag": hit.group(1),
                            "text": hit.group(2).strip()[:160],
                        })
                if len(env_usage) < MAX_ENV_USAGE:
                    for rgx, via in ENV_PATTERNS:
                        if rgx.search(line):
                            env_usage.append({"file": rel, "line": lineno, "via": via})
                            break
    return {
        "todos": todos,
        "todo_count": len(todos),
        "env_usage": env_usage,
        "code_files": code_files,
        "files_seen": files_seen,
        "test_files": test_files,
        "newest_mtime": newest,
        "truncated": files_seen >= MAX_FILES,
    }


def project_facts(root) -> dict:
    """Факты о дереве, которые нужны health: тесты, CI, lock-файлы, .env.example."""
    root = os.fspath(root)
    tops, dirs = set(), set()
    try:
        for e in os.scandir(root):
            tops.add(e.name)
            if e.is_dir(follow_symlinks=False):
                dirs.add(e.name)
    except OSError:
        pass
    env_examples = sorted(n for n in tops if n.lower() in
                          {".env.example", ".env.sample", ".env.template", "env.example"})
    has_ci = os.path.isdir(os.path.join(root, *CI_DIR))
    return {
        "src_dirs": sorted(dirs),
        "has_ci": has_ci,
        "env_examples": env_examples,
        "marker_names": sorted(n for n in tops if n in LOCK_FILES),
        "has_env_example": bool(env_examples),
    }


CI_DIR = (".github", "workflows")
LOCK_FILES = {"poetry.lock", "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml",
              "yarn.lock", "uv.lock", "Cargo.lock", "packages.lock.json"}
