"""Воскрешение проекта: окружение, зависимости, .env.example.

Только созидание: .venv/npm install ставятся в песочницу проекта,
.env.example пишется лишь если его нет. Код пользователя не трогаем.
"""
import json
import os
import re
import subprocess
import sys

from .source_scan import CODE_EXT, SKIP_DIRS

# ищем чтения переменных окружения: os.getenv c именем в кавычках,
# os.environ по ключу и process.env в js-стиле
ENV_PATTERNS = (
    re.compile(r"""os\.getenv\s*\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""os\.environ\.get\s*\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""os\.environ\s*\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]"""),
    re.compile(r"\bprocess\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"""process\.env\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]"""),
)

MAX_FILES = 400          # патологический проект не сканируем до посинения
MAX_ENV_NAMES = 30


def find_env_names(root) -> list:
    """Собирает имена переменных окружения из исходников проекта."""
    root = str(root)
    names = []
    seen_files = 0
    for base, dirs, files in os.walk(root):
        # tests пропускаем намеренно: фикстуры набиты фейковыми env-именами
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                   and d.lower() not in ("tests", "test")]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in CODE_EXT:
                continue
            if seen_files >= MAX_FILES:
                return names
            seen_files += 1
            try:
                with open(os.path.join(base, name), "r", encoding="utf-8",
                          errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            for pattern in ENV_PATTERNS:
                for match in pattern.finditer(text):
                    var = match.group(1)
                    if var and var not in names:
                        names.append(var)
                        if len(names) >= MAX_ENV_NAMES:
                            return names
    return names


def generate_env_example(root) -> list:
    """Пишет .env.example из найденных имён. Существующий не трогаем."""
    root = str(root)
    target = os.path.join(root, ".env.example")
    if os.path.exists(target):
        return []
    names = find_env_names(root)
    if not names:
        return []
    lines = ["# Сгенерировано Project Butler по чтениям env в коде.",
             "# Заполни значения и при желании переименуй в .env (добавь .env в .gitignore!).", ""]
    lines += [name + "=" for name in names]
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return names


def _run(cmd, cwd, log) -> bool:
    """Запускает команду, стримит вывод в лог. False — ненулевой код выхода."""
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        log("✗ не смог запустить: " + " ".join(cmd) + " — " + str(exc))
        return False
    for line in proc.stdout:                       # noqa: B007 — стрим до конца
        line = line.rstrip()
        if line:
            log("  " + line[:160])
    code = proc.wait()
    if code:
        log(f"✗ код выхода {code}")
        return False
    return True


def plan(root, stacks) -> dict:
    """Что собирается делать воскрешатель — показать юзеру до запуска."""
    root = str(root)
    steps = []
    if "python" in stacks:
        steps.append("создать .venv")
        for marker in ("requirements.txt", "pyproject.toml"):
            if os.path.exists(os.path.join(root, marker)):
                steps.append("поставить зависимости из " + marker)
                break
    if "node" in stacks and os.path.exists(os.path.join(root, "package.json")):
        steps.append("npm install")
    steps.append("сгенерировать .env.example из чтений env (если его нет)")
    return {"steps": steps}


def resurrect(root, stacks, log) -> dict:
    """Полный цикл воскрешения. log(text) — колбэк прогресса. Синхронный, зовётся из потока."""
    root = str(root)
    result = {"venv": False, "deps": False, "env_names": [], "notes": []}
    python = sys.executable

    if "python" in stacks:
        venv_dir = os.path.join(root, ".venv")
        if os.path.isdir(venv_dir):
            log("• .venv уже существует — не трогаю")
            result["venv"] = True
        else:
            log("• создаю .venv…")
            if _run([python, "-m", "venv", ".venv"], root, log):
                result["venv"] = True
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        if not os.path.exists(venv_python):
            venv_python = os.path.join(venv_dir, "bin", "python")
        req = os.path.join(root, "requirements.txt")
        if os.path.exists(req) and os.path.exists(venv_python):
            log("• ставлю зависимости из requirements.txt (это может занять минуты)…")
            result["deps"] = _run([venv_python, "-m", "pip", "install", "-r", "requirements.txt"],
                                  root, log)
        elif os.path.exists(os.path.join(root, "pyproject.toml")) and os.path.exists(venv_python):
            log("• ставлю проект из pyproject.toml…")
            result["deps"] = _run([venv_python, "-m", "pip", "install", "-e", "."], root, log)

    if "node" in stacks and os.path.exists(os.path.join(root, "package.json")):
        if os.path.isdir(os.path.join(root, "node_modules")):
            log("• node_modules уже есть — npm install пропускаю")
            result["deps"] = True
        else:
            log("• npm install (это может занять минуты)…")
            result["deps"] = _run(["npm", "install"], root, log)

    log("• собираю .env.example из чтений env в коде…")
    names = generate_env_example(root)
    if names:
        log("• записаны переменные: " + ", ".join(names))
        result["env_names"] = names
    else:
        result["notes"].append("env-переменных не нашлось или .env.example уже существует")
        log("• .env.example не понадобился")
    log("✓ воскрешение завершено")
    return result
