"""Детектор Python-проектов по файлам-маркерам (только чтение)."""
import re

# pip-ссылки вида https://user:pass@host — пароль в базу не пишем
_AUTH_IN_URL = re.compile(r"(https?://)[^/\s@]+@")

MARKERS = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "poetry.lock"}
ENTRY_POINTS = ("main.py", "app.py", "bot.py", "manage.py", "run.py")
VENVS = (".venv", "venv")


def detect(path, entries):
    names = {e.name for e in entries}
    markers = sorted(MARKERS & names)
    has_py = any(n.endswith(".py") for n in names)
    if not markers and not has_py:
        return None
    facts = {"stack": "python", "markers": markers}
    req = path / "requirements.txt"
    if req.is_file():
        try:
            text = req.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        facts["deps"] = [_AUTH_IN_URL.sub(r"\1***@", l.strip()) for l in text.splitlines()
                         if l.strip() and not l.strip().startswith("#")]
    for ep in ENTRY_POINTS:
        if ep in names:
            facts["entry"] = ep
            break
    dirs = {e.name for e in entries if e.is_dir()}
    facts["has_venv"] = bool(set(VENVS) & dirs)
    return facts
