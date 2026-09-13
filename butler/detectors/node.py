"""Детектор Node-проектов: читает package.json (только чтение)."""
import json


def detect(path, entries):
    names = {e.name for e in entries}
    if "package.json" not in names:
        return None
    facts = {"stack": "node"}
    try:
        pkg = json.loads((path / "package.json").read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return facts
    facts["pkg_name"] = pkg.get("name", "?")
    facts["deps_count"] = len(pkg.get("dependencies") or {})
    facts["scripts"] = sorted((pkg.get("scripts") or {}).keys())
    dirs = {e.name for e in entries if e.is_dir()}
    facts["has_node_modules"] = "node_modules" in dirs
    return facts
