"""Диагностика окружения проекта: только чтение, ничего не устанавливает."""
import json
import re
import shutil
import subprocess
from pathlib import Path

SYSTEM_TOOLS = ("git", "node", "npm", "python", "py", "ffmpeg", "ffprobe",
                "dotnet", "docker", "code")


def git_ahead_behind(status_line) -> tuple:
    """'## main...origin/main [ahead 1, behind 2]' → (1, 2). Без скобок → (0, 0)."""
    ahead = behind = 0
    m = re.search(r"ahead\s+(\d+)", status_line or "")
    if m:
        ahead = int(m.group(1))
    m = re.search(r"behind\s+(\d+)", status_line or "")
    if m:
        behind = int(m.group(1))
    return ahead, behind


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
        # ok=None — проверка не состоялась (таймаут, нет сети): не считаем проблемой
        checks.append({"check": name, "ok": None if ok is None else bool(ok),
                       "detail": str(detail)})

    if "git" in stacks:
        git_exe = tools.get("git")
        add("git в PATH", git_exe is not None, git_exe or "не найден")
        branch = facts.get("branch", "?")
        add("текущая ветка", branch not in ("?", "", None), branch)
        if git_exe:
            code, out = _run([git_exe, "status", "--porcelain"], path, timeout)
            if code == 0:
                dirty = len([l for l in out.splitlines() if l.strip()])
                add("незакоммиченное", dirty == 0,
                    "чисто" if not dirty else f"{dirty} файлов ждут коммита")
            code, out = _run([git_exe, "status", "-sb"], path, timeout)
            if code == 0:
                first = out.splitlines()[0] if out else ""
                if "..." not in first:
                    add("синхронизация с origin", None, "нет upstream-ветки")
                else:
                    ahead, behind = git_ahead_behind(first)
                    add("синхронизация с origin", ahead == 0 and behind == 0,
                        "синхронизировано" if ahead == 0 and behind == 0
                        else f"впереди на {ahead}, позади на {behind}")
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
            # устаревшие пакеты: ходит в PyPI, потому с щедрым таймаутом и мягким исходом
            code, out = _run([str(venv), "-m", "pip", "list", "--outdated"], path, 40)
            if code is None:
                add("устаревшие пакеты (pip)", None, out or "не успел проверить")
            elif code == 0:
                stale = max(0, len([l for l in out.splitlines() if l.strip()]) - 2)
                add("устаревшие пакеты (pip)", stale == 0,
                    "все свежие" if not stale else f"устарело: {stale}")
            else:
                add("устаревшие пакеты (pip)", None, out[:80] or "pip отказался отвечать")
            # аудит уязвимостей: отдельный пакет pip-audit — если стоит, проверяем
            code, out = _run([str(venv), "-m", "pip_audit", "--version"], path, 15)
            if code != 0:
                add("аудит уязвимостей (pip)", None, "pip-audit не установлен (pip install pip-audit)")
            else:
                code, out = _run([str(venv), "-m", "pip_audit", "-l", "--progress-spinner", "off"],
                                 path, 90)
                ok = code == 0 and "No known vulnerabilities" in out
                add("аудит уязвимостей (pip)", ok if code == 0 else None,
                    out.splitlines()[-1][:120] if out else "проверено")

    if "node" in stacks or "js" in stacks:
        node_exe = tools.get("node")
        add("node в PATH", node_exe is not None, node_exe or "не найден")
        npm = tools.get("npm")
        if npm and facts.get("has_node_modules"):
            # npm на Windows — это .cmd, зовём через cmd /c
            code, out = _run(["cmd", "/c", npm, "ls", "--depth=0"], path, timeout * 2)
            add("npm ls --depth=0", code == 0, out or "дерево зависимостей целое")
        pkg = Path(path) / "package.json"
        if pkg.exists() and node_exe:
            try:
                with open(pkg, "r", encoding="utf-8", errors="replace") as fh:
                    engines = (json.load(fh).get("engines") or {}).get("node")
            except (OSError, ValueError):
                engines = None
            if engines:
                code, out = _run([node_exe, "--version"], path, timeout)
                m = re.match(r"v?(\d+)", out or "")
                installed = int(m.group(1)) if (code == 0 and m) else None
                required = re.search(r"(\d+)", engines)
                if installed is None or not required:
                    add("версия node vs engines", None, f"не смог сравнить с {engines}")
                else:
                    ok = installed >= int(required.group(1))
                    add("версия node vs engines", ok,
                        f"требуется {engines}, установлена v{installed}")
        if npm and facts.get("has_node_modules"):
            code, out = _run(["cmd", "/c", npm, "outdated", "--depth=0"], path, 40)
            if code is None:
                add("устаревшие пакеты (npm)", None, out or "не успел проверить")
            else:
                stale = len([l for l in out.splitlines() if l.strip()])
                add("устаревшие пакеты (npm)", code == 0 and stale == 0,
                    "все свежие" if stale == 0 else f"устарело: {stale}")
            # аудит уязвимостей: npm умеет сам, ходит в реестр
            code, out = _run(["cmd", "/c", npm, "audit", "--json"], path, 60)
            if code is None:
                add("аудит уязвимостей (npm)", None, "не успел проверить")
            elif out.strip():
                try:
                    vulns = (json.loads(out).get("metadata") or {}).get("vulnerabilities") or {}
                except ValueError:
                    vulns = {}
                if not vulns:
                    add("аудит уязвимостей (npm)", None, "ответ не разобрался")
                else:
                    bad = int(vulns.get("critical", 0) or 0) + int(vulns.get("high", 0) or 0)
                    total = sum(int(v or 0) for v in vulns.values())
                    add("аудит уязвимостей (npm)", bad == 0,
                        "уязвимостей нет" if total == 0 else
                        f"всего {total}, критичных+высоких: {bad}")

    entry = facts.get("entry")
    if entry:
        here = Path(path) / entry
        nested = facts.get("nested_root")
        there = Path(path) / nested / entry if nested else None
        ok = here.is_file() or (there is not None and there.is_file())
        add("точка входа", ok, entry + ("" if ok else " — файл не найден"))

    if "docker" in stacks:
        add("docker в PATH", tools.get("docker") is not None, tools.get("docker") or "не найден")
        compose = Path(path) / "docker-compose.yml"
        if not compose.exists():
            compose = Path(path) / "compose.yml"
        if compose.exists() and tools.get("docker"):
            code, out = _run([tools["docker"], "compose", "-f", compose.name,
                              "config", "--quiet"], path, timeout * 2)
            add("docker compose config", code == 0, out or "конфигурация валидна")
        elif not compose.exists():
            add("docker compose config", None, "docker-compose.yml не найден")

    return checks


def format_report(rec, checks) -> str:
    lines = [f"Диагностика: {rec.get('name')} — {rec.get('path')}", ""]
    for c in checks:
        mark = "◐" if c["ok"] is None else ("✓" if c["ok"] else "✗")
        lines.append(f"  {mark} {c['check']}: {c['detail'] or 'ок'}")
    broken = sum(1 for c in checks if c["ok"] is False)
    lines.append("")
    lines.append("всё зелёное" if not broken else f"проблем: {broken}")
    return "\n".join(lines)
