"""Вес проекта на диске: общий размер и «мусорные» директории (кандидаты на очистку)."""
import os

# Директории, которые можно безопасно сносить и пересоздавать (venv, сборки, кэши)
JUNK_DIRS = {
    "node_modules", ".venv", "venv", "env", "__pycache__", ".next", "out",
    "dist", "build", "target", "models", "downloads", "output", "temp",
    "obj", "bin", ".gradle", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "site-packages", "coverage", ".tox", "vendor",
}

MAX_FILES = 300_000  # защита от монструозных деревьев (тренировочные датасеты и пр.)


def dir_size(root, skip=()):
    """Сумма байт в дереве. skip — имена поддиректорий, которые не трогаем."""
    total = 0
    stack = [os.fspath(root)]
    skip = set(skip)
    seen = 0
    truncated = False
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            seen += 1
            if seen > MAX_FILES:
                truncated = True
                break
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if e.name not in skip:
                        stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    total += e.stat(follow_symlinks=False).st_size
            except OSError:
                continue
        if truncated:
            break
    return total, truncated


def project_disk(root) -> dict:
    """Вес проекта: total / junk / топ мусорных папок. Вложенный мусор считается внутри верхнего."""
    try:
        entries = [e for e in os.scandir(root)]
    except OSError:
        return {"total": 0, "junk": 0, "parts": [], "truncated": False}
    junk_total = 0
    code_total = 0
    parts = []
    truncated = False
    for e in entries:
        try:
            if e.is_symlink():
                continue
            if e.is_dir(follow_symlinks=False):
                size, trunc = dir_size(e.path)
                truncated = truncated or trunc
                if e.name in JUNK_DIRS:
                    junk_total += size
                    parts.append({"name": e.name, "bytes": size})
                else:
                    code_total += size
            elif e.is_file(follow_symlinks=False):
                code_total += e.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    parts.sort(key=lambda p: -p["bytes"])
    return {
        "total": code_total + junk_total,
        "junk": junk_total,
        "parts": parts[:6],
        "truncated": truncated,
    }


def human_bytes(num) -> str:
    """1_234_567 -> '1.2 MB'."""
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} TB"
