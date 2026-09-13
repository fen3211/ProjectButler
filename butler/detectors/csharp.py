"""Детектор C#: .sln / .csproj в верхнем уровне."""


def detect(path, entries):
    hits = sorted(e.name for e in entries if e.is_file()
                  and (e.name.endswith(".sln") or e.name.endswith(".csproj")))
    if not hits:
        return None
    return {"stack": "csharp", "markers": hits}
