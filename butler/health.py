"""Health-score 0-100 и статус проекта. Правила — PLAN.md, раздел MVP 0.1.

Штрафы (база 100):
  -20 нет README
  -20 нет git
  -20 в коде читается окружение (os.getenv / process.env), но нет .env.example
  -20 зависимости объявлены, но проект протух (>180 дней без активности)
  -10 зависимости объявлены, но нет следов установки (.venv / node_modules / lock)

Бонусы (доказывают, что проект живой, а не «стартанул и бросил»):
  +5 есть тесты (tests/ или test_*.py / *.test.ts)
  +5 есть CI (.github/workflows)
  +5 есть .env.example при чтении env
  +3 зафиксированы версии (lock-файл)

Статусы:
  unknown    — ни одного маркера стека (пустая папка)
  broken     — score < 40
  abandoned  — нет активности дольше stale_days
  alive      — всё остальное
"""
import time

STALE_DAYS = 180
DAY = 86400.0

PENALTY_NO_README = 20
PENALTY_NO_GIT = 20
PENALTY_ENV_UNDOCUMENTED = 20
PENALTY_STALE_DEPS = 20
PENALTY_NOT_INSTALLED = 10

BONUS_TESTS = 5
BONUS_CI = 5
BONUS_ENV_EXAMPLE = 5
BONUS_LOCK = 3

# Приоритет «главного» стека — для кластеров в визуале и группировки в отчёте
STACK_PRIORITY = ("python", "node", "csharp", "go", "docker", "js", "git")

TEST_DIR_NAMES = {"tests", "test", "spec", "specs", "__tests__"}
LOCK_FILES = {"poetry.lock", "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml",
              "yarn.lock", "uv.lock", "Cargo.lock", "packages.lock.json"}
ENV_EXAMPLE_NAMES = {".env.example", ".env.sample", ".env.template", "env.example"}


def _val(p, key, default=None):
    """Достаёт поле из dict (запись sqlite) или из объекта Project."""
    if isinstance(p, dict):
        return p.get(key, default)
    return getattr(p, key, default)


def _facts(p) -> dict:
    facts = _val(p, "facts", {}) or {}
    return facts if isinstance(facts, dict) else {}


# Вес стека: маркеры важнее случайных файлов-сирот.
# В `портфолио` рядом с package.json лежит fetch3.py — главный стек там node, а не python.
STACK_BASE_WEIGHT = {
    "python": 1, "node": 1, "csharp": 1, "go": 1, "docker": 1, "js": 1, "git": 0,
}
MARKER_WEIGHT = (
    (("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"), "node", 3),
    (("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"), "python", 3),
    (("go.mod",), "go", 3),
    (("Dockerfile", "docker-compose.yml", "compose.yml"), "docker", 2),
)


def days_idle(p, now=None) -> int:
    """Сколько дней проект молчит (по последней активности, если она есть)."""
    now = now if now is not None else time.time()
    stamp = _val(p, "activity") or _val(p, "mtime") or 0.0
    if not stamp:
        return 0
    return max(0, int((now - stamp) / DAY))


def _has_tests(p) -> bool:
    facts = _facts(p)
    if TEST_DIR_NAMES & set(facts.get("src_dirs", [])):
        return True
    return bool(facts.get("test_files") or facts.get("has_tests"))


def _has_ci(p) -> bool:
    return bool(_facts(p).get("has_ci"))


def _declares_deps(p) -> bool:
    facts = _facts(p)
    if facts.get("deps") or facts.get("deps_count"):
        return True
    markers = set(facts.get("markers", []))
    return bool(markers & {"requirements.txt", "package.json", "pyproject.toml",
                           "go.mod", "setup.py", "Pipfile"})


def _has_lock(p) -> bool:
    facts = _facts(p)
    names = set(facts.get("marker_names", []))
    return bool(names & LOCK_FILES) or bool(facts.get("lock"))


def _installed_evidence(p) -> bool:
    """Следы установки зависимостей: venv / node_modules / lock-файл."""
    facts = _facts(p)
    return bool(facts.get("has_venv") or facts.get("has_node_modules")) or _has_lock(p)


def _env_example(p) -> bool:
    facts = _facts(p)
    names = set(facts.get("marker_names", [])) | set(facts.get("env_examples", []))
    return bool(names & ENV_EXAMPLE_NAMES) or bool(facts.get("has_env_example"))


def primary_stack(p) -> str:
    """Главный стек — по весу маркеров, при равенстве — по STACK_PRIORITY."""
    stacks = list(_val(p, "stacks", []) or [])
    if not stacks:
        return "unknown"
    facts = _facts(p)
    markers = set(facts.get("markers", []) or [])
    if facts.get("pkg_name") or facts.get("scripts"):
        markers.add("package.json")
    if facts.get("deps") or facts.get("module"):
        markers.add("go.mod" if facts.get("module") else "requirements.txt")
    if any(m.endswith((".sln", ".csproj")) for m in markers):
        markers.add(".sln")

    weights = {}
    for stack in stacks:
        weights[stack] = STACK_BASE_WEIGHT.get(stack, 1)
    for names, stack, bonus in MARKER_WEIGHT:
        if stack in weights and markers & set(names):
            weights[stack] += bonus
    if ".sln" in markers and "csharp" in weights:
        weights["csharp"] += 3
    if ".py" in markers and "python" in weights:
        weights["python"] += 2

    order = {name: i for i, name in enumerate(STACK_PRIORITY)}

    def rank(stack):
        return (-weights.get(stack, 0), order.get(stack, len(order)), stack)

    return sorted(stacks, key=rank)[0]


def evaluate(p, now=None, stale_days=STALE_DAYS) -> dict:
    """Считает score/status/why для проекта. Чистая функция: ни файлов, ни сети."""
    now = now if now is not None else time.time()
    stacks = _val(p, "stacks", []) or []
    idle = days_idle(p, now)
    penalties, bonuses = [], []

    if not stacks:
        return {
            "score": 0,
            "status": "unknown",
            "idle_days": idle,
            "penalties": [],
            "bonuses": [],
            "why": ["ни одного маркера стека не найдено"],
        }

    if not _val(p, "has_readme", False):
        penalties.append((PENALTY_NO_README, "нет README"))
    if "git" not in stacks:
        penalties.append((PENALTY_NO_GIT, "нет git"))

    env_in_code = bool(_val(p, "env_usage") or _facts(p).get("env_usage"))
    if env_in_code and not _env_example(p):
        penalties.append((PENALTY_ENV_UNDOCUMENTED, "код читает env, а .env.example нет"))
    elif env_in_code:
        bonuses.append((BONUS_ENV_EXAMPLE, "конфигурация задокументирована"))

    stale = idle > stale_days
    if stale and _declares_deps(p):
        penalties.append((PENALTY_STALE_DEPS, f"протух: {idle} дней без активности"))
    if _declares_deps(p) and not _installed_evidence(p):
        penalties.append((PENALTY_NOT_INSTALLED, "зависимости объявлены, но не установлены"))

    if _has_tests(p):
        bonuses.append((BONUS_TESTS, "есть тесты"))
    if _has_ci(p):
        bonuses.append((BONUS_CI, "есть CI"))
    if _has_lock(p):
        bonuses.append((BONUS_LOCK, "зафиксированы версии (lock)"))

    score = 100 - sum(v for v, _ in penalties) + sum(v for v, _ in bonuses)
    score = max(0, min(100, score))

    if score < 40:
        status = "broken"
    elif stale:
        status = "abandoned"
    else:
        status = "alive"

    return {
        "score": score,
        "status": status,
        "idle_days": idle,
        "penalties": [{"points": v, "why": w} for v, w in penalties],
        "bonuses": [{"points": v, "why": w} for v, w in bonuses],
        "why": [w for _, w in penalties] or ["претензий нет — проект в форме"],
    }


STATUS_ORDER = {"broken": 0, "abandoned": 1, "unknown": 2, "alive": 3}


def worst_first(records, key="status"):
    """Сортировка «сначала то, что сгнило» — для отчёта и визуала."""
    def _k(r):
        st = _val(r, key, "unknown") or "unknown"
        return (STATUS_ORDER.get(st, 9), _val(r, "score", 0) or 0, _val(r, "name", "") or "")
    return sorted(records, key=_k)
