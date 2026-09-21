"""Сканер папки с проектами: маркеры сверху + ограниченный поиск вглубь, только чтение."""
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .detectors import detect_all
from .disk import project_disk
from .health import evaluate
from .source_scan import project_facts, scan_sources

def _has_code_stack(stacks) -> bool:
    """Есть ли среди стеков хоть что-то кроме служебного git/js-маркера."""
    return any(st in ("python", "node", "csharp", "go", "docker") for st in stacks)


# Папки с такими именами проектами не считаем
SKIP_NAMES = {".git", ".venv", "venv", "__pycache__", "node_modules"}

# Маркерные имена для глубокого поиска (только имена, без чтения содержимого)
DEEP_MARKERS = {
    "requirements.txt": "python", "pyproject.toml": "python", "setup.py": "python",
    "setup.cfg": "python", "Pipfile": "python",
    "package.json": "node", "go.mod": "go",
    "Dockerfile": "docker", "docker-compose.yml": "docker", "compose.yml": "docker",
    "manifest.json": "js",  # browser extension без package.json
    ".git": "git",
}


def _deep_names(path, max_entries=3000, max_depth=3):
    """Собирает маркерные имена до max_depth вглубь. Лимит записей — защита от гигантских деревьев."""
    found = set()
    has_py = False
    has_js = False
    stack = [(str(path), 0)]
    seen = 0
    while stack and seen < max_entries:
        cur, depth = stack.pop()
        try:
            with os.scandir(cur) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            seen += 1
            if seen > max_entries:
                break
            if e.name in SKIP_NAMES:
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if e.name == ".git":
                    found.add(".git")
                elif depth + 1 < max_depth and not e.name.startswith("."):
                    stack.append((e.path, depth + 1))
            elif e.name in DEEP_MARKERS:
                found.add(e.name)
            elif e.name.endswith(".py"):
                has_py = True
            elif e.name.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs")):
                has_js = True
            elif e.name.lower().startswith("readme"):
                found.add("readme")
            elif e.name == ".env":
                found.add(".env")
    return found, has_py, has_js


@dataclass
class Project:
    name: str
    path: str
    stacks: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    mtime: float = 0.0
    size_top: int = 0  # суммарный размер файлов верхнего уровня (быстро, без рекурсии)
    has_readme: bool = False
    has_env: bool = False
    activity: float = 0.0        # время последней активности (свежий файл / git index)
    todos: list = field(default_factory=list)
    todo_count: int = 0
    env_usage: list = field(default_factory=list)
    health: dict = field(default_factory=dict)

    @property
    def updated_str(self) -> str:
        stamp = self.activity or self.mtime
        return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d") if stamp else "-"

    @property
    def score(self) -> int:
        return self.health.get("score", 0)

    @property
    def status(self) -> str:
        return self.health.get("status", "unknown")

    def to_dict(self) -> dict:
        """Плоская запись — то, что видят store/index/MCP."""
        return {
            "name": self.name, "path": self.path, "stacks": self.stacks,
            "facts": self.facts, "mtime": self.mtime, "activity": self.activity,
            "size_top": self.size_top, "has_readme": self.has_readme,
            "has_env": self.has_env, "todos": self.todos,
            "todo_count": self.todo_count, "env_usage": self.env_usage,
            "health": self.health,
        }


def _git_activity(path) -> float:
    """Свежесть git-метаданных: index и refs обновляются при каждом коммите."""
    best = 0.0
    for rel in (".git/index", ".git/HEAD"):
        try:
            best = max(best, (path / rel).stat().st_mtime)
        except OSError:
            continue
    heads = path / ".git" / "refs" / "heads"
    try:
        for ref in heads.rglob("*"):
            if ref.is_file():
                best = max(best, ref.stat().st_mtime)
    except OSError:
        pass
    return best


def scan(root) -> list:
    """Сканирует непосредственные подпапки root, возвращает список Project."""
    root = Path(root)
    found = []
    for child in sorted(root.iterdir()):
        # Симлинки не преследуем: не уходим в чужие деревья через ссылки/джанкшены
        if child.is_symlink():
            continue
        if not child.is_dir() or child.name.startswith(".") or child.name in SKIP_NAMES:
            continue
        try:
            entries = list(child.iterdir())
        except OSError:
            continue
        stacks, facts = detect_all(child, entries)
        size_top = 0
        names_lower = set()
        for e in entries:
            try:
                if e.is_file():
                    names_lower.add(e.name.lower())
                    size_top += e.stat().st_size
            except OSError:
                continue
        if not _has_code_stack(stacks):
            # Проект может лежать на уровень глубже:
            # GostChecker/gost_checker, StableDiffusion/stable-diffusion-webui,
            # или код в подпапке при .git в корне (ProjectButler/butler)
            for sub in sorted(entries):
                if sub.is_symlink():
                    continue
                try:
                    is_dir = sub.is_dir()
                except OSError:
                    continue
                if not is_dir or sub.name.startswith(".") or sub.name in SKIP_NAMES:
                    continue
                try:
                    sub_entries = list(sub.iterdir())
                except OSError:
                    continue
                s, f = detect_all(sub, sub_entries)
                if not s:
                    continue
                for st in s:
                    if st not in stacks:
                        stacks.append(st)
                for k, v in f.items():
                    facts.setdefault(k, v)
                facts.setdefault("nested_root", sub.name)
                for se in sub_entries:
                    try:
                        if se.is_file():
                            names_lower.add(se.name.lower())
                    except OSError:
                        continue
        if not _has_code_stack(stacks):
            # Маркеры лежат еще глубже (GostChecker/gost_checker/parsers) —
            # ограниченный поиск по именам, без чтения содержимого
            deep, deep_py, deep_js = _deep_names(child)
            for marker in sorted(deep):
                st = DEEP_MARKERS.get(marker)
                if st and st not in stacks:
                    stacks.append(st)
            if deep_py and "python" not in stacks:
                stacks.append("python")
            if deep_js and "js" not in stacks and "node" not in stacks:
                stacks.append("js")
            if stacks:
                facts.setdefault("deep_scan", True)
                facts.setdefault("branch", "?") if "git" in stacks else None
            if "readme" in deep:
                names_lower.add("readme.md")
            if ".env" in deep:
                names_lower.add(".env")
        try:
            mtime = child.stat().st_mtime
        except OSError:
            mtime = 0.0

        # Эффективный корень кода: если проект нашёлся на уровень глубже, читаем его
        code_root = child
        nested = facts.get("nested_root")
        if nested:
            candidate = child / nested
            if candidate.is_dir():
                code_root = candidate

        tree = project_facts(code_root)
        for key, value in tree.items():
            facts.setdefault(key, value)
        sources = scan_sources(child)
        facts["source_scan"] = {
            "code_files": sources["code_files"],
            "files_seen": sources["files_seen"],
            "test_files": sources["test_files"],
            "truncated": sources["truncated"],
        }
        facts.setdefault("test_files", sources["test_files"])
        facts.setdefault("todos", sources["todos"][:120])
        facts.setdefault("secrets", sources["secrets"])
        facts.setdefault("secret_count", sources["secret_count"])
        facts["disk"] = project_disk(child)
        if sources["env_usage"]:
            facts.setdefault("env_usage", sources["env_usage"])

        # .env лежит рядом, а .gitignore его не упоминает — риск закоммитить секреты
        if ".env" in names_lower and ".gitignore" in names_lower:
            try:
                gi = (child / ".gitignore").read_text(encoding="utf-8", errors="ignore")
                facts["env_leak_risk"] = ".env" not in gi
            except OSError:
                facts["env_leak_risk"] = True
        elif ".env" in names_lower and "git" in stacks:
            facts["env_leak_risk"] = True                   # git есть, .gitignore нет вообще

        activity = max(mtime, sources["newest_mtime"], _git_activity(child))
        record = {
            "name": child.name, "path": str(child), "stacks": stacks, "facts": facts,
            "mtime": activity, "size_top": size_top,
            "has_readme": any(n == "readme.md" or n.startswith("readme") for n in names_lower),
            "has_env": ".env" in names_lower,
            "todo_count": sources["todo_count"], "env_usage": sources["env_usage"],
        }
        found.append(Project(
            name=child.name,
            path=str(child),
            stacks=stacks,
            facts=facts,
            mtime=mtime,
            activity=activity,
            size_top=size_top,
            has_readme=record["has_readme"],
            has_env=record["has_env"],
            todos=sources["todos"],
            todo_count=sources["todo_count"],
            env_usage=sources["env_usage"],
            health=evaluate(record),
        ))
    return found
