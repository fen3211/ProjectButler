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
    if not isinstance(pkg, dict):
        return facts
    facts["pkg_name"] = pkg.get("name", "?")
    deps = pkg.get("dependencies")
    facts["deps_count"] = len(deps) if isinstance(deps, dict) else 0
    scripts = pkg.get("scripts")
    facts["scripts"] = sorted(scripts.keys()) if isinstance(scripts, dict) else []
    dirs = {e.name for e in entries if e.is_dir()}
    facts["has_node_modules"] = "node_modules" in dirs
    return facts
