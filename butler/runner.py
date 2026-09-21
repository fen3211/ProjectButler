"""Детект команды запуска проекта — для кнопки Run в один клик.

Ничего не запускаем сами: только решаем, ЧЕМ это запускается.
"""
import json
import os

_MARKERS = ("main.py", "app.py", "bot.py", "run.py", "server.py", "manage.py")


def _package_json_start(root) -> list | None:
    """npm start / npm run dev из package.json; None — скриптов нет."""
    path = os.path.join(str(root), "package.json")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return None
    if "start" in scripts:
        return ["npm", "start"]
    if "dev" in scripts:
        return ["npm", "run", "dev"]
    return None


def detect_command(root, stacks) -> dict | None:
    """Чем запускать проект: {"cmd": [...], "kind": str} или None, если не понятно."""
    root = str(root)
    stacks = list(stacks or [])

    if "node" in stacks:
        cmd = _package_json_start(root)
        if cmd:
            return {"cmd": cmd, "kind": "npm"}

    if "python" in stacks:
        for marker in _MARKERS:
            if os.path.exists(os.path.join(root, marker)):
                return {"cmd": ["py", "-3.12", marker], "kind": "python"}
        # venv-питон с установленной точкой входа — крайний случай, не угадываем

    if "docker" in stacks and os.path.exists(os.path.join(root, "docker-compose.yml")):
        return {"cmd": ["docker", "compose", "up"], "kind": "docker"}

    if "go" in stacks and os.path.exists(os.path.join(root, "go.mod")):
        return {"cmd": ["go", "run", "."], "kind": "go"}

    return None
