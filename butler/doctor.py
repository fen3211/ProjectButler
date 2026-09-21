"""Диагностика окружения проекта: только чтение, ничего не устанавливает."""
import shutil
import subprocess
from pathlib import Path

SYSTEM_TOOLS = ("git", "node", "npm", "python", "py", "ffmpeg", "ffprobe",
                "dotnet", "docker", "code")


def system_tools() -> dict:
    """Что из инструментов доступно в PATH: {имя: путь или None}."""
    return {name: shutil.which(name) for name in SYSTEM_TOOLS}


def _venv_python(path) -> Path:
    for name in (".venv", "venv"):
        cand = Path(path) / name / "Scripts" / "python.exe"
        if cand.is_file():
            return cand
    return None


def _run(cmd, cwd, timeout):
    """Один безопасный вызов: без shell, с таймаутом, обрезанный вывод."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
        out = (proc.stdout + proc.stderr).strip()
        return proc.returncode, out[:400]
    except subprocess.TimeoutExpired:
        return None, f"таймаут {timeout}s"
    except OSError as exc:
        return None, f"не запустился: {exc}"


def diagnose(rec, timeout=20) -> list:
    """Список проверок для проекта: [{check, ok, detail}]."""
    checks = []
    path = rec.get("path", "")
    facts = rec.get("facts") or {}
    stacks = rec.get("stacks", []) or []
    tools = system_tools()

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})

    if "git" in stacks:
        add("git в PATH", tools.get("git") is not None, tools.get("git") or "не найден")
        branch = facts.get("branch", "?")
        add("текущая ветка", branch not in ("?", "", None), branch)
    else:
        add("git-репозиторий", False, "нет .git — крести кнопкой в UI")

    if "python" in stacks:
        interp = tools.get("python") or tools.get("py")
        add("python в PATH", interp is not None, interp or "не найден")
        venv = _venv_python(path)
        add("виртуальное окружение", venv is not None,
            str(venv) if venv else "нет .venv/venv")
        if venv and facts.get("deps"):
            code, out = _run([str(venv), "-m", "pip", "check"], path, timeout)
            add("pip check", code == 0, out or "зависимости целые")

    if "node" in stacks or "js" in stacks:
        add("node в PATH", tools.get("node") is not None, tools.get("node") or "не найден")
        npm = tools.get("npm")
        if npm and facts.get("has_node_modules"):
            # npm на Windows — это .cmd, зовём через cmd /c
            code, out = _run(["cmd", "/c", npm, "ls", "--depth=0"], path, timeout * 2)
            add("npm ls --depth=0", code == 0, out or "дерево зависимостей целое")

    entry = facts.get("entry")
    if entry:
        here = Path(path) / entry
        nested = facts.get("nested_root")
        there = Path(path) / nested / entry if nested else None
        ok = here.is_file() or (there is not None and there.is_file())
        add("точка входа", ok, entry + ("" if ok else " — файл не найден"))

    if "docker" in stacks:
        add("docker в PATH", tools.get("docker") is not None, tools.get("docker") or "не найден")

    return checks


def format_report(rec, checks) -> str:
    lines = [f"Диагностика: {rec.get('name')} — {rec.get('path')}", ""]
    for c in checks:
        mark = "✓" if c["ok"] else "✗"
        lines.append(f"  {mark} {c['check']}: {c['detail'] or 'ок'}")
    broken = sum(1 for c in checks if not c["ok"])
    lines.append("")
    lines.append("всё зелёное" if not broken else f"проблем: {broken}")
    return "\n".join(lines)
