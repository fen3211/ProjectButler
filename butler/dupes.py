"""Поиск дубликатов: схожесть по зависимостям, теглайну README и именам директорий."""
import re

STOP_WORDS = {
    "the", "and", "for", "with", "this", "that", "your", "from", "local", "project",
    "or", "not", "are", "you", "all", "can", "has", "web", "app", "tool", "tools",
    "из", "для", "или", "как", "что", "все", "это", "его", "при", "без", "она", "они",
    "по", "на", "не", "в", "и", "с", "у", "к", "о", "от", "до",
}

MIN_SHARED = 3          # меньше трёх общих токенов — это случайное совпадение, а не дубль
THRESHOLD = 0.30


def norm_dep(line: str) -> str:
    """'faster-whisper>=1.0.3' -> 'faster-whisper'."""
    name = re.split(r"[<>=~!\[\];\s]", line.strip(), 1)[0].strip().lower()
    return re.sub(r"[-_.]+", "-", name)


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (text or "").lower())
            if w not in STOP_WORDS}


def tokens(rec) -> set:
    """Мешок признаков проекта: dep:<имя>, tag:<слово>, dir:<папка>."""
    facts = rec.get("facts") or {}
    out = set()
    for dep in facts.get("deps", []) or []:
        name = norm_dep(str(dep))
        if name and not name.startswith(("git+", "http", "dev:")):
            out.add("dep:" + name)
        elif name.startswith("dev:"):
            out.add("dep:" + name[4:])
    for word in _words(rec.get("tagline") or ""):
        out.add("tag:" + word)
    for folder in facts.get("src_dirs", []) or []:
        low = str(folder).lower()
        if low not in (".git", ".github", ".claude"):
            out.add("dir:" + low)
    return out


def find_dupes(records, threshold=THRESHOLD) -> list:
    """Пары похожих проектов: score = Жаккар по токенам, shared — что совпало."""
    recs = list(records)
    bags = {rec.get("path", rec.get("name")): tokens(rec) for rec in recs}
    links = []
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            a, b = bags[recs[i].get("path")], bags[recs[j].get("path")]
            if not a or not b:
                continue
            shared = a & b
            if len(shared) < MIN_SHARED:
                continue
            score = len(shared) / len(a | b)
            if score >= threshold:
                links.append({
                    "a": recs[i].get("name"), "b": recs[j].get("name"),
                    "score": round(score, 3),
                    "shared": sorted(shared)[:10],
                })
    return sorted(links, key=lambda l: -l["score"])
