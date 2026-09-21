"""Генерация README из кода и зависимостей. Локальный шаблон, без облака.

Пишет файл только если README нет — рукописный не трогаем никогда.
"""
import os

README_NAMES = {"readme.md", "readme.txt", "readme.rst", "readme"}


def readme_exists(root) -> bool:
    """README уже есть? Смотрим любые написания, рукописный не угадаешь — не трогаем."""
    root = str(root)
    try:
        for name in os.listdir(root):
            if name.lower() in README_NAMES:
                return True
    except OSError:
        pass
    return False


def build_readme(rec, run_plan) -> str:
    """Текст README из фактов сканера + детекта команды запуска."""
    name = rec.get("name", "проект")
    stacks = [s for s in (rec.get("stacks") or []) if s != "git"] or ["не определён"]
    facts = rec.get("facts") or {}
    deps = [str(d) for d in (facts.get("deps") or [])]
    entry = facts.get("entry") or ""
    todos = rec.get("todo_count", 0) or 0
    tagline = (rec.get("tagline") or "").strip().splitlines()[0] if rec.get("tagline") else ""

    lines = [f"# {name}", ""]
    if tagline:
        lines += [tagline, ""]
    else:
        lines += ["Проект найден и описан сканером Project Butler.", ""]

    lines += ["## Стек", ""]
    lines += [f"- {s}" for s in stacks]
    lines.append("")

    if deps:
        lines += ["## Зависимости", ""]
        lines += [f"- {d}" for d in deps[:25]]
        lines.append("")
    else:
        lines += ["## Зависимости", "", "Внешних зависимостей не найдено.", ""]

    lines += ["## Запуск", ""]
    if run_plan:
        lines.append("```bat")
        lines.append(" ".join(run_plan["cmd"]))
        lines.append("```")
    elif entry:
        lines.append(f"Точка входа: `{entry}`.")
    else:
        lines.append("Команда запуска не определилась автоматически — допиши своими словами.")
    lines.append("")

    if todos:
        lines += [f"> В коде {todos} TODO-маркеров — загляни в Project Butler за списком.", ""]

    lines += ["---", "", "*Каркас сгенерирован Project Butler — перепиши своими словами, "
              "файл больше не перезаписывается.*"]
    return "\n".join(lines) + "\n"


def generate(root, rec, run_plan) -> dict:
    """Создаёт README.md, если его нет. Возвращает {"written", "path", "reason"}."""
    root = str(root)
    if readme_exists(root):
        return {"written": False, "reason": "README уже существует — рукописный не трогаю"}
    text = build_readme(rec, run_plan)
    target = os.path.join(root, "README.md")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(text)
    return {"written": True, "path": target, "reason": "сгенерирован"}
