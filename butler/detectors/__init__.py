"""Реестр детекторов стека. Контракт: detect(path, entries) -> dict | None."""
from . import csharp, docker, git, go, node, python

_DETECTORS = (python, node, docker, git, csharp, go)


def detect_all(path, entries):
    """Прогоняет все детекторы, возвращает (stacks, facts)."""
    stacks = []
    facts = {}
    for det in _DETECTORS:
        try:
            hit = det.detect(path, entries)
        except OSError:
            continue
        if hit:
            stacks.append(hit.pop("stack"))
            facts.update(hit)
    return stacks, facts
