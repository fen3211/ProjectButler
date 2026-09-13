"""Детектор Go: go.mod, читает имя модуля."""


def detect(path, entries):
    if "go.mod" not in {e.name for e in entries}:
        return None
    facts = {"stack": "go"}
    try:
        lines = (path / "go.mod").read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return facts
    for line in lines:
        if line.startswith("module "):
            facts["module"] = line.split(None, 1)[1]
            break
    return facts
