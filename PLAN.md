# Project Butler — план разработки (единый источник правды)

> Этот файл — главный ориентир при написании кода. Все решения сверять с ним.
> Обновлять по мере реализации: отмечать [x] выполненное.

## 1. Что это
Локальный пилот по папке с проектами (по умолчанию `D:\Projects`).
Видит все проекты, говорит что живо / что сгнило, умеет воскрешать одной кнопкой.
Всё локально, ничего в облако не отправляет. Windows-first.

## 2. Целевой пользователь
Разработчик с 10+ папками пет-проектов / фриланса / учебы. Первый пользователь — автор.

## 3. Функционал

### MVP 0.1 — "Зеркало" (только показывает, ничего не чинит)
- [x] Сканер папок: обход на 1 уровень вглубь, игнор `node_modules`, `.venv`, `__pycache__`, `.git/objects` (фактически — до 3 уровней)
- [x] Детекторы по файлам-маркерам:
  - Node: `package.json`
  - Python: `requirements.txt` / `pyproject.toml` / `*.py`
  - Docker: `Dockerfile` / `docker-compose.yml`
  - Git: `.git`
  - C#: `*.sln` / `*.csproj`
  - Go: `go.mod`
- [x] Сбор полей: name, path, stacks[], mtime, size, has_readme, has_env, has_venv/node_modules, git_status
- [x] Health-score 0-100: -20 нет README, -20 нет гита, -20 протухшие зависимости (эвристика), -20 нет .env.example при наличии чтения env в коде
- [x] Дашборд: список + фильтр по стеку/статусу/дате + поиск по имени/README/зависимостям/TODO (роль дашборда играет галактика + док + `/api/search`)
- [x] Карточка проекта: статус (alive/broken/unknown/abandoned>6мес), кнопки Открыть в VSCode / папке / терминале
- [x] CLI: `python -m butler scan D:\Projects` печатает таблицу

### 0.2 — "Доктор" (диагностика, только чтение)
- [x] Python: venv есть/нет, `pip check` (без установки)
- [x] Node: `npm ls`, версия node в package.json vs установленная
- [x] Docker: `docker compose config` валиден/нет
- [x] Git: uncommitted, behind/ahead, текущая ветка
- [x] TODO-грепер: TODO/FIXME/HACK/XXX с файлом и строкой
- [x] Устаревшие зависимости: `npm outdated`, `pip list --outdated` (только чтение; таймаут — мягкий «◐», не падение)
- [x] Теги + заметки пользователя (sqlite) — в карточке, фильтр галактики по тегу, MCP `butler_tags`

### 1.0 — "Воскрешение"
- [x] Python: создать .venv, поставить зависимости в песочнице, сгенерить .env.example из `os.getenv` поиска
- [x] Node: `npm install` в песочнице, подсказка `.nvmrc` (npm install — да, .nvmrc — нет)
- [x] Генерация README из кода + зависимостей (локальный шаблон, без облака; рукописный не перезаписывается)
- [x] Run в один клик: определение команды (scripts.start/dev, main.py/app.py/bot.py, docker compose up), лог в UI
- [x] Кнопка Resurrect → бранч `butler/fix-env` — сознательно НЕ делаем: бранч на проекте с незакоммиченными изменениями опаснее прямой работы в папке; окружение ставится в песочницу (.venv/node_modules), код не трогается

### НЕ делаем в MVP
Облако, аккаунты, авто-фиксы кода, AI в облаке, поддержка всех языков.

## 4. Архитектура
- Backend: Python (сканер, анализаторы, sqlite)
- Frontend MVP: Python + Web UI на localhost (браузер). Позже — Tauri.
- Хранение: `~/.project-butler/butler.db` (sqlite) + `config.json` (папки сканирования)
- API MVP: tiny HTTP `localhost:17373` или просто генерация `report.json` + статичный `index.html`

```
D:\Projects\ProjectButler\
  PLAN.md            # этот файл
  README.md
  run.bat
  butler/
    __init__.py
    __main__.py      # CLI вход: scan
    scanner.py       # обход папок
    detectors/
      __init__.py
      python.py
      node.py
      docker.py
      git.py
      csharp.py
      go.py
    health.py        # скоринг 0-100 + статус
    todos.py         # grep TODO
    store.py         # sqlite
    server.py        # (позже) tiny API
  ui/
    index.html
    app.js
```

## 5. Логика скана (порядок)
1. list dirs → 2. detect по маркерам → 3. health-правила → 4. сохранить в sqlite → 5. UI читает sqlite
2. Перескан: по кнопке + вотчер раз в час (позже)

## 6. План по шагам
### День 1 — сканер + база
- [x] Папка + PLAN.md + git init
- [x] `butler/scanner.py` + `detectors/*` (python/node/docker/git/csharp/go/js + поиск вглубь до 3 уровней)
- [x] `butler/store.py` (sqlite `~/.project-butler/butler.db`)
- [x] `python -m butler scan` работает на реальных папках (7/8 стеков верно, WebPortfolio пуст — честный unknown)
### День 2 — health + UI
- [x] `health.py` + `todos.py` (score 0-100, статусы alive/abandoned/broken/unknown, TODO-грепер с игнором vendor-папок)
- [x] минимальный UI: вместо статичного `index.html` сделана «галактика проектов» (`ui/galaxy.html` + `ui/galaxy.js`, Canvas 2D + ручная 3D-проекция, без CDN)
### День 3 — действия
- [x] Открыть в VSCode / папке / терминале (кнопки в карточке галактики, `POST /api/open` с guard по корню)
- [x] Теги + заметки
- [x] `run.bat`, иконка в трее (опционально) — трей не делали, run.bat есть

## 7. Проверка готовности (definition of done MVP 0.1)
- [x] Скан `D:\Projects` находит GostChecker, AIAgent, FreelanceBot и др.
- [x] У каждого верно определен стек
- [x] Health-score считается по правилам выше
- [x] Поиск находит проект по зависимости/TODO/README (`/api/search`)
- [x] Кнопки открытия работают на Windows

## 8. Текущий статус
- 2026-09-13: создана папка, написан PLAN.md, git init, приватный репо https://github.com/fen3211/ProjectButler засинхронен (ветка main). Следующее: scaffold сканера (День 1).
- 2026-09-14: День 1 готов — сканер + 7 детекторов + sqlite + CLI scan/list, проверка на D:\Projects (7/8 верно). Следующее: День 2 (health.py + todos.py + UI).
- 2026-09-14: ревью Day-1 — 5 фиксов (краш на битом package.json, понятная ошибка + exit 2 на плохой папке, norm_root против дублей в базе, пропуск симлинков/джанкшенов, затирание паролей в pip-URL); самотест 5/5 PASS.
- 2026-09-21: День 2–3 + сверх плана: `health.py` (штрафы/бонусы, статусы), `source_scan.py` (TODO + чтение env + последняя активность из git index/refs), `index.py` (фид galaxy.json, детерминированная раскладка), `store.py` (именованные колонки + ALTER-миграции), `mcp_server.py` (stdio-JSON-RPC без SDK, 8 инструментов), `webserver.py` (только 127.0.0.1, `/api/open` с guard), UI «галактика» (тёмная тема, кластеры, карточка, фильтры). CLI: scan/list/report/todos/export/ui/mcp. 23 юнит-теста + `scripts/smoke.py` (e2e) — зелёные. Баг по ходу: позиционный INSERT без имён колонок ломался на ALTER-миграции — переведён на именованный INSERT; `_within` отклоняет пустой путь и чужие диски.
- 2026-09-21 (вечер): редизайн UI в стиле «Тёмная материя» (пикер папок с деревом дисков, асинхронный скан через `ScanState` + `/api/scan-status` — большие диски больше не вешают UI), живой космос (параллакс, метеоры, дифракционные лучи, чёрные дыры для мёртвых, TODO-рои, поиск-затмение по содержимому, гиперпространство при смене корня, инерция камеры, авто-дрейф). Функционал: теги+заметки (sqlite `meta`, MCP `butler_tags`), Resurrect (.venv/npm install + .env.example из чтений env, тесты при генерации пропускаются), Run в один клик (детект команды + лог процесса), дайджест изменений, живой фид по версии файла. Фиксы: `.env.example` ищется и в корне проекта при вложенном code_root; поиски по базе нормализуют путь через `norm_root`. 39 юнит-тестов + смоук — зелёные.
