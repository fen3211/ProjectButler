"""Детектор Docker: Dockerfile / compose-файлы."""


def detect(path, entries):
    names = {e.name for e in entries}
    markers = sorted(
        ({"Dockerfile", "docker-compose.yml", "docker-compose.yaml",
          "compose.yml", "compose.yaml", ".dockerignore"} & names)
        | {n for n in names if n.endswith(".Dockerfile") or n.startswith("Dockerfile.")}
    )
    if not markers:
        return None
    return {"stack": "docker", "markers": markers}
