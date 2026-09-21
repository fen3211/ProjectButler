"""Настройки: корни сканирования, пути к данным. Приоритет: аргумент > env > config.json > дефолт."""
import json
import os
from pathlib import Path

HOME = Path.home() / ".project-butler"
CONFIG_PATH = HOME / "config.json"
FEED_PATH = HOME / "galaxy.json"
DB_PATH = HOME / "butler.db"
SETTINGS_PATH = HOME / "settings.json"
FALLBACK_ROOT = r"D:\Projects"

DEFAULT_SETTINGS = {"theme": "darkmatter", "lang": "ru", "custom": {}, "watch": False, "multi": []}


def load_settings() -> dict:
    """Настройки UI: тема, язык, свой стиль. Чужие ключи сохраняем."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return dict(DEFAULT_SETTINGS)
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)
    out = dict(DEFAULT_SETTINGS)
    out.update({k: v for k, v in data.items() if k in ("theme", "lang", "custom", "watch", "multi")})
    if not isinstance(out["custom"], dict):
        out["custom"] = {}
    if not isinstance(out["multi"], list):
        out["multi"] = []
    return out


def save_settings(settings) -> dict:
    """Пишет настройки (только известные ключи), возвращает сохранённое."""
    out = dict(DEFAULT_SETTINGS)
    out.update({k: v for k, v in (settings or {}).items()
                if k in ("theme", "lang", "custom", "watch", "multi")})
    if out["theme"] not in ("darkmatter", "deepspace", "mars", "observatory", "custom"):
        out["theme"] = "darkmatter"
    if out["lang"] not in ("ru", "en"):
        out["lang"] = "ru"
    if not isinstance(out["custom"], dict):
        out["custom"] = {}
    out["watch"] = bool(out["watch"])
    if not isinstance(out["multi"], list):
        out["multi"] = []
    out["multi"] = [str(r) for r in out["multi"]][:6]
    HOME.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


def remember_root(root) -> None:
    """Запоминает корень как дефолтный, чтобы `butler mcp` без аргументов знал, где смотреть."""
    cfg = load_config()
    roots = [r for r in cfg.get("roots", []) if r != str(root)]
    cfg["roots"] = [str(root)] + roots[:4]
    cfg["last_root"] = str(root)
    save_config(cfg)


def known_roots() -> list:
    """История корней для селектора в UI: сначала последний, без дублей, только живые пути."""
    cfg = load_config()
    out = []
    for candidate in [cfg.get("last_root"), *(cfg.get("roots") or [])]:
        if candidate and os.path.isdir(str(candidate)) and str(candidate) not in out:
            out.append(str(candidate))
    return out


def resolve_root(root=None, use_config=True) -> str:
    """Кто первый встал — того и тапки: аргумент, env BUTLER_ROOT, конфиг, D:\\Projects."""
    if root:
        return str(root)
    if os.environ.get("BUTLER_ROOT"):
        return os.environ["BUTLER_ROOT"]
    if use_config:
        cfg = load_config()
        if cfg.get("last_root"):
            return str(cfg["last_root"])
        for candidate in cfg.get("roots", []):
            if os.path.isdir(candidate):
                return str(candidate)
    if os.path.isdir(FALLBACK_ROOT):
        return FALLBACK_ROOT
    return os.getcwd()
