"""Детектор git: читает .git/HEAD напрямую, без запуска git (быстро)."""


def detect(path, entries):
    if ".git" not in {e.name for e in entries}:
        return None
    facts = {"stack": "git", "branch": "?"}
    try:
        head = (path / ".git" / "HEAD").read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return facts
    if head.startswith("ref:"):
        facts["branch"] = head.rsplit("/", 1)[-1]
    elif head:
        facts["branch"] = "detached@" + head[:7]
    return facts
