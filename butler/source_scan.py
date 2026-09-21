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

# Утёкшие секреты: реальные значения, а не плейсхолдеры из *.example
SECRET_PATTERNS = (
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,40}\b"), "telegram-bot-token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "openai-key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"), "google-api-key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws-access-key"),
    (re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[:=]\s*[\"']"
                r"([A-Za-z0-9_\-+/=.]{12,})[\"']"), "generic-secret"),
    (re.compile(r"(?im)^\s*[A-Z0-9_]{3,}_(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*(\S{10,})\s*$"),
     "env-value"),
)
PLACEHOLDER_WORDS = ("your", "changeme", "change-me", "example", "sample", "dummy",
                     "insert", "placeholder", "xxx", "todo", "test", "fake", "none", "null")

MAX_FILES = 900
MAX_BYTES = 512 * 1024
MAX_TODOS = 300
MAX_ENV_USAGE = 8
MAX_SECRETS = 30


def _looks_real(value: str) -> bool:
    """Отсекает плейсхолдеры и код: your_key_here, changeme, self.model_key[...]."""
    low = value.strip("'\"").lower()
    if any(word in low for word in PLACEHOLDER_WORDS):
        return False
    if any(ch in low for ch in "()[]{}"):                 # это python-выражение, а не секрет
        return False
    if any(ch in low for ch in ",;"):                     # аргументы вызова — тоже код
        return False
    return True


def _find_secrets(line: str, rel: str, lineno: int, found: list) -> None:
    for rgx, kind in SECRET_PATTERNS:
        m = rgx.search(line)
        if not m:
            continue
        value = m.group(1) if m.lastindex else m.group(0)
        if not _looks_real(value):
            continue
        if kind == "env-value" and not any(ch.isdigit() for ch in value):
            continue                       # util.natural_sort_key = util.natural_sort_key — это код
        found.append({
            "file": rel, "line": lineno, "kind": kind,
            "preview": value[:4] + "…" + value[-2:],
        })
        return                                                # одна строка = одна находка


def _read_text(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return None


def scan_sources(root) -> dict:
    """Обходит дерево root, возвращает todos / env_usage / secrets / счётчики / newest_mtime."""
    root = os.fspath(root)
    todos, env_usage, secrets = [], [], []
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
            if (len(todos) >= MAX_TODOS and len(env_usage) >= MAX_ENV_USAGE
                    and len(secrets) >= MAX_SECRETS):
                continue
            text = _read_text(path)
            if text is None:
                continue
            is_example = rel.endswith((".example", ".sample", ".template", ".dist"))
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
                if len(secrets) < MAX_SECRETS and not is_example:
                    _find_secrets(line, rel, lineno, secrets)
    return {
        "todos": todos,
        "todo_count": len(todos),
        "env_usage": env_usage,
        "secrets": secrets,
        "secret_count": len(secrets),
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
