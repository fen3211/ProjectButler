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
- [ ] Сканер папок: обход на 1 уровень вглубь, игнор `node_modules`, `.venv`, `__pycache__`, `.git/objects`
- [ ] Детекторы по файлам-маркерам:
  - Node: `package.json`
  - Python: `requirements.txt` / `pyproject.toml` / `*.py`
  - Docker: `Dockerfile` / `docker-compose.yml`
  - Git: `.git`
  - C#: `*.sln` / `*.csproj`
  - Go: `go.mod`
- [ ] Сбор полей: name, path, stacks[], mtime, size, has_readme, has_env, has_venv/node_modules, git_status
- [ ] Health-score 0-100: -20 нет README, -20 нет гита, -20 протухшие зависимости (эвристика), -20 нет .env.example при наличии чтения env в коде
- [ ] Дашборд: список + фильтр по стеку/статусу/дате + поиск по имени/README/зависимостям/TODO
- [ ] Карточка проекта: статус (alive/broken/unknown/abandoned>6мес), кнопки Открыть в VSCode / папке / терминале
- [ ] CLI: `python -m butler scan D:\Projects` печатает таблицу

### 0.2 — "Доктор" (диагностика, только чтение)
- [ ] Python: venv есть/нет, `pip check` (без установки)
- [ ] Node: `npm ls`, версия node в package.json vs установленная
- [ ] Docker: `docker compose config` валиден/нет
- [ ] Git: uncommitted, behind/ahead, текущая ветка
- [ ] TODO-грепер: TODO/FIXME/HACK/XXX с файлом и строкой
- [ ] Устаревшие зависимости: `npm outdated`, `pip list --outdated` (только чтение)
- [ ] Теги + заметки пользователя (sqlite)

### 1.0 — "Воскрешение"
- [ ] Кнопка Resurrect → бранч `butler/fix-env`
- [ ] Python: создать .venv, поставить зависимости в песочнице, сгенерить .env.example из `os.getenv` поиска
- [ ] Node: `npm install` в песочнице, подсказка `.nvmrc`
- [ ] Генерация README из кода + зависимостей (локальный шаблон, без облака)
- [ ] Run в один клик: определение команды (scripts.start/dev, main.py/app.py/bot.py, docker compose up), лог в UI

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
- [ ] `butler/scanner.py` + `detectors/*`
- [ ] `butler/store.py` (sqlite)
- [ ] `python -m butler scan` работает на реальных папках
### День 2 — health + UI
- [ ] `health.py` + `todos.py`
- [ ] минимальный `ui/index.html`: список, карточка, поиск
### День 3 — действия
- [ ] Открыть в VSCode / папке / терминале
- [ ] Теги + заметки
- [ ] `run.bat`, иконка в трее (опционально)

## 7. Проверка готовности (definition of done MVP 0.1)
- [ ] Скан `D:\Projects` находит GostChecker, AIAgent, FreelanceBot и др.
- [ ] У каждого верно определен стек
- [ ] Health-score считается по правилам выше
- [ ] Поиск находит проект по зависимости/TODO
- [ ] Кнопки открытия работают на Windows

## 8. Текущий статус
- 2026-09-13: создана папка, написан PLAN.md, git init, приватный репо https://github.com/fen3211/ProjectButler засинхронен (ветка main). Следующее: scaffold сканера (День 1).
