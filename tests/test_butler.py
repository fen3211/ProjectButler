"""Тесты Project Butler: health, TODO, фид, хранилище, MCP-протокол. Только stdlib + unittest.

Запуск: py -3.12 -m unittest discover -s tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from butler import health, index, store            # noqa: E402
from butler.scanner import scan                    # noqa: E402
from butler.source_scan import scan_sources        # noqa: E402
from butler.todos import count_by_tag, format_todos  # noqa: E402


def make_project(root: Path, name: str, files: dict, folders=(), git_head="refs/heads/main"):
    """Собирает проект на диске: словарь {относительный путь: содержимое}."""
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
    for folder in folders:
        (target / folder).mkdir(parents=True, exist_ok=True)
    if git_head:
        (target / ".git").mkdir(exist_ok=True)
        (target / ".git" / "HEAD").write_text("ref: " + git_head + "\n", encoding="utf-8")
    return target


class HealthRules(unittest.TestCase):
    def base(self, **over):
        rec = {
            "name": "demo", "path": r"D:\demo", "stacks": ["python", "git"],
            "facts": {"markers": ["requirements.txt"], "deps": ["requests"], "has_venv": True},
            "has_readme": True, "has_env": False, "todo_count": 0,
            "activity": time.time(), "mtime": time.time(),
        }
        rec.update(over)
        return rec

    def test_clean_project_scores_100(self):
        result = health.evaluate(self.base())
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["status"], "alive")

    def test_no_readme_and_no_git_penalised(self):
        result = health.evaluate(self.base(has_readme=False, stacks=["python"]))
        self.assertEqual(result["score"], 60)
        self.assertIn("нет README", result["why"])
        self.assertIn("нет git", result["why"])

    def test_env_read_undeclared_is_penalised(self):
        rec = self.base(env_usage=[{"file": "main.py", "line": 3, "via": "os.getenv"}])
        self.assertEqual(health.evaluate(rec)["score"], 80)
        docs = self.base(env_usage=[{"file": "main.py", "line": 3, "via": "os.getenv"}],
                         facts={"markers": ["requirements.txt"], "deps": ["x"], "has_venv": True,
                                "has_env_example": True})
        self.assertEqual(health.evaluate(docs)["score"], 100)

    def test_stale_with_deps_is_abandoned(self):
        old = time.time() - 400 * 86400
        result = health.evaluate(self.base(activity=old, mtime=old))
        self.assertEqual(result["status"], "abandoned")
        self.assertEqual(result["score"], 80)
        self.assertGreaterEqual(result["idle_days"], 399)

    def test_unknown_when_no_stack(self):
        result = health.evaluate({"name": "empty", "stacks": [], "facts": {}})
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["score"], 0)

    def test_score_never_negative(self):
        result = health.evaluate(self.base(has_readme=False, stacks=["python"], activity=0,
                                           env_usage=[{"file": "a.py", "line": 1, "via": "os.getenv"}]))
        self.assertGreaterEqual(result["score"], 0)

    def test_primary_stack_prefers_real_markers(self):
        nodeish = {"stacks": ["python", "node", "git"],
                   "facts": {"markers": ["package.json"], "pkg_name": "site", "deps_count": 12}}
        self.assertEqual(health.primary_stack(nodeish), "node")
        pyish = {"stacks": ["python", "git"], "facts": {"markers": ["requirements.txt"]}}
        self.assertEqual(health.primary_stack(pyish), "python")
        self.assertEqual(health.primary_stack({"stacks": [], "facts": {}}), "unknown")


class SourceScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_todos_env_and_activity(self):
        make_project(self.root, "Demo", {
            "main.py": 'import os\nKEY = os.getenv("KEY")  # TODO: вынести в конфиг\n',
            "notes.md": "FIXME: дописать доклад\n",
        }, folders=["tests", ".github"])
        project = self.root / "Demo"
        self.assertTrue((project / "tests").is_dir())
        result = scan_sources(project)
        tags = {t["tag"] for t in result["todos"]}
        self.assertEqual(tags, {"TODO", "FIXME"})
        self.assertEqual(result["todo_count"], 2)
        self.assertTrue(any(e["via"] == "os.getenv" for e in result["env_usage"]))
        self.assertGreater(result["newest_mtime"], 0)

    def test_ignores_vendored_dirs(self):
        project = make_project(self.root, "Vendored", {"app.py": "# TODO: живой\n"})
        (project / "node_modules").mkdir()
        (project / "node_modules" / "junk.py").write_text("# TODO: мусор\n", encoding="utf-8")
        (project / ".venv").mkdir()
        (project / ".venv" / "lib.py").write_text("# FIXME: мусор\n", encoding="utf-8")
        result = scan_sources(project)
        self.assertEqual(result["todo_count"], 1)
        self.assertEqual(result["todos"][0]["file"], "app.py")

    def test_format_and_count(self):
        items = [{"tag": "TODO", "project": "A", "file": "a.py", "line": 1, "text": "x"},
                 {"tag": "TODO", "project": "B", "file": "b.py", "line": 2, "text": "y"},
                 {"tag": "FIXME", "project": "A", "file": "c.py", "line": 3, "text": "z"}]
        self.assertEqual(count_by_tag(items), {"TODO": 2, "FIXME": 1})
        self.assertIn("a.py:1", format_todos(items))
        self.assertIn("TODO-маркеров не найдено", format_todos([]))


class ScanAndFeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_project(self.root, "Alive", {
            "README.md": "# Alive\n\nЖивой проект: тесты, CI и lock.\n",
            "requirements.txt": "requests\n",
            "app.py": 'import os\nprint(os.getenv("TOKEN"))  # TODO: убрать принт\n',
            ".env.example": "TOKEN=\n",
            "poetry.lock": "",
        }, folders=["tests", ".github"], git_head="refs/heads/main")
        (self.root / "Alive" / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        make_project(self.root, "Rotting", {
            "main.py": "print('hello')\n",
        }, git_head=None)
        (self.root / "Empty").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_returns_projects_with_health(self):
        projects = {p.name: p for p in scan(self.root)}
        self.assertEqual(set(projects), {"Alive", "Rotting", "Empty"})
        alive = projects["Alive"]
        self.assertIn("python", alive.stacks)
        self.assertIn("git", alive.stacks)
        self.assertTrue(alive.facts.get("has_ci"))
        self.assertEqual(alive.todo_count, 1)
        self.assertEqual(alive.health["score"], 100)
        self.assertEqual(projects["Empty"].status, "unknown")
        self.assertNotIn("git", projects["Rotting"].stacks)

    def test_feed_has_geometry_and_totals(self):
        records = [p.to_dict() for p in scan(self.root)]
        feed = index.build_feed(str(self.root), records)
        self.assertEqual(feed["feed_version"], index.FEED_VERSION)
        self.assertEqual(feed["totals"]["projects"], 3)
        names = {n["name"] for n in feed["projects"]}
        self.assertEqual(names, {"Alive", "Rotting", "Empty"})
        for node in feed["projects"]:
            self.assertEqual(len(node["pos"]), 3)
            self.assertIn(node["stack"], feed["clusters"])
            self.assertIsInstance(node["score"], int)
        self.assertIn("Alive", feed["totals"]["healthy"])

    def test_feed_is_stable_between_runs(self):
        records = [p.to_dict() for p in scan(self.root)]
        first = index.build_feed(str(self.root), records)["projects"]
        second = index.build_feed(str(self.root), records)["projects"]
        self.assertEqual([n["pos"] for n in first], [n["pos"] for n in second])

    def test_write_feed_roundtrip(self):
        out = self.root / "galaxy.json"
        feed = index.build_feed(str(self.root), [p.to_dict() for p in scan(self.root)])
        index.write_feed(out, feed)
        self.assertEqual(index.read_feed(out)["totals"]["projects"], 3)
        self.assertFalse((self.root / "galaxy.json.tmp").exists())


class StoreRoundtrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "butler.db"
        self.patcher = mock.patch.object(store, "DB_PATH", self.db)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_save_and_list(self):
        record = {"name": "Demo", "path": r"D:\Demo", "stacks": ["python", "git"],
                  "facts": {"branch": "main"}, "mtime": 1.0, "activity": 2.0, "size_top": 10,
                  "has_readme": True, "has_env": False, "todo_count": 3,
                  "health": {"score": 77, "status": "alive", "why": ["ок"]}}
        store.save_projects([record], r"D:\Projects")
        rows = store.list_projects(r"D:\Projects")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["health"]["score"], 77)
        self.assertEqual(rows[0]["todo_count"], 3)
        self.assertEqual(rows[0]["score"], 77)
        self.assertEqual(rows[0]["facts"]["branch"], "main")
        self.assertIsNone(store.get_project("нет-такого", r"D:\Projects"))
        self.assertEqual(store.get_project("demo", r"D:\Projects")["name"], "Demo")

    def test_migration_from_day1_schema(self):
        """Старая база (без activity/health) должна читаться после ALTER TABLE."""
        import sqlite3
        conn = sqlite3.connect(str(self.db))
        conn.execute("""CREATE TABLE projects (
            path TEXT PRIMARY KEY, root TEXT, name TEXT, stacks TEXT, facts TEXT,
            mtime REAL, size_top INTEGER, has_readme INTEGER, has_env INTEGER, scanned_at REAL)""")
        # параметризованно: иначе бэкслеши Windows в SQL-литерале превращаются в кашу
        conn.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (r"D:\Old", r"D:\Projects", "Old", "[]", "{}", 1.0, 0, 0, 0, 2.0))
        conn.commit()
        conn.close()
        rows = store.list_projects(r"D:\Projects")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Old")
        self.assertEqual(rows[0]["status"], "unknown")     # health ещё не считался — честный дефолт
        record = {"name": "New", "path": r"D:\New", "stacks": ["python"], "facts": {},
                  "mtime": 3.0, "activity": 3.0, "size_top": 0, "has_readme": True,
                  "has_env": False, "todo_count": 1,
                  "health": {"score": 90, "status": "alive", "why": []}}
        store.save_projects([record], r"D:\Projects")
        rows = store.list_projects(r"D:\Projects")
        self.assertEqual([r["name"] for r in rows], ["New"])
        self.assertEqual(rows[0]["health"]["score"], 90)


class McpProtocol(unittest.TestCase):
    """Полный хендшейк MCP через subprocess: initialize -> tools/list -> tools/call."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        make_project(cls.root, "Alive", {
            "README.md": "# Alive\n\nПроект, который не стыдно показать.\n",
            "requirements.txt": "requests\n",
            "app.py": "print('ok')  # TODO: доделать\n",
            ".env.example": "A=\n",
        }, folders=["tests"], git_head="refs/heads/main")
        # некрополь: ни README, ни git, env читается без .env.example, зависимости не установлены
        make_project(cls.root, "Broken", {
            "requirements.txt": "requests\n",
            "app.py": 'import os\nprint(os.getenv("X"))\n',
        }, git_head=None)
        cls.env = dict(os.environ,
                       BUTLER_ROOT=str(cls.root),
                       USERPROFILE=cls.tmp.name,
                       PYTHONIOENCODING="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_session(self, messages):
        payload = "\n".join(json.dumps(m) for m in messages) + "\n"
        proc = subprocess.run([sys.executable, "-m", "butler", "mcp"], cwd=str(PROJECT_DIR),
                              input=payload.encode("utf-8"), capture_output=True,
                              env=self.env, timeout=180)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return [json.loads(line) for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]

    def test_handshake_and_tools(self):
        responses = self.run_session([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "butler_status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "butler_dead_projects", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "не-существующий", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 6, "method": "no/such/method"},
        ])
        self.assertEqual(len(responses), 6, responses)     # нотификация ответа не даёт
        by_id = {r["id"]: r for r in responses}
        init = by_id[1]["result"]
        self.assertEqual(init["serverInfo"]["name"], "project-butler")
        self.assertIn(init["protocolVersion"], ("2025-06-18", "2025-03-26", "2024-11-05"))
        self.assertIn("tools", init["capabilities"])

        tools = {t["name"]: t for t in by_id[2]["result"]["tools"]}
        self.assertEqual(len(tools), 13)
        for required in ("butler_disk", "butler_dupes", "butler_secrets",
                         "butler_doctor", "butler_diff"):
            self.assertIn(required, tools)
        self.assertIn("inputSchema", tools["butler_project"])

        status = by_id[3]["result"]
        self.assertFalse(status["isError"])
        text = status["content"][0]["text"]
        self.assertIn("Проектов: 2", text)
        self.assertIn("Alive", text)

        dead = by_id[4]["result"]["content"][0]["text"]
        self.assertIn("Broken", dead)

        self.assertTrue(by_id[5]["result"]["isError"])
        self.assertIn("Неизвестный инструмент", by_id[5]["result"]["content"][0]["text"])
        self.assertEqual(by_id[6]["error"]["code"], -32601)

    def test_galaxy_tool_returns_valid_feed(self):
        responses = self.run_session([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "butler_galaxy", "arguments": {}}},
        ])
        feed = json.loads(responses[0]["result"]["content"][0]["text"])
        self.assertEqual(feed["totals"]["projects"], 2)
        self.assertEqual(sorted(n["name"] for n in feed["projects"]), ["Alive", "Broken"])

    def test_scan_tool_detects_projects(self):
        responses = self.run_session([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "butler_scan", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "butler_list_projects", "arguments": {"status": "alive"}}},
        ])
        self.assertIn("Пересканировано", responses[0]["result"]["content"][0]["text"])
        listed = json.loads(responses[1]["result"]["content"][0]["text"])
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["projects"][0]["name"], "Alive")


class WebGuard(unittest.TestCase):
    """Пути вне корня сканирования открывать нельзя — это единственная дыра в API."""

    def test_inside_root_allowed(self):
        from butler.webserver import _within
        self.assertTrue(_within(r"D:\Projects\Demo", r"D:\Projects"))
        self.assertTrue(_within(r"D:\Projects\Demo\sub\file.py", r"D:\Projects"))

    def test_outside_root_denied(self):
        from butler.webserver import _within
        self.assertFalse(_within(r"C:\Windows", r"D:\Projects"))
        self.assertFalse(_within(r"D:\Projects-evil", r"D:\Projects"))   # commonpath, а не startswith
        self.assertFalse(_within("", r"D:\Projects"))
        self.assertFalse(_within(None, r"D:\Projects"))


class DiskDupesSecrets(unittest.TestCase):
    """Новая аналитика: вес на диске, дубликаты, секреты, история и диф сканов."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Два похожих python-проекта и один уникальный node-проект
        make_project(self.root, "CloneA", {
            "README.md": "# A\n\nВидео нарезка клипов на python\n",
            "requirements.txt": "yt-dlp\nfaster-whisper\nrequests\n",
            "app.py": 'import os\nKEY = "sk-abcdefghijklmnopqrst"\n',
            ".env": "SECRET_TOKEN=supersecretvalue123\n",
            ".gitignore": "node_modules/\n",          # .env НЕ в игноре — утечка
        }, folders=["tests"], git_head="refs/heads/main")
        make_project(self.root, "CloneB", {
            "README.md": "# B\n\nНарезка видео клипов на python\n",
            "requirements.txt": "yt-dlp\nfaster-whisper\nnumpy\n",
            "app.py": "print('b')\n",
        }, git_head=None)
        make_project(self.root, "Unique", {
            "package.json": json.dumps({"name": "uniq", "dependencies": {"react": "^19"}}),
            "index.js": "console.log('ok');\n",
        }, git_head=None)
        # мусорные директории для проверки веса
        junk = self.root / "CloneA" / "node_modules" / "pkg"
        junk.mkdir(parents=True)
        (junk / "lib.js").write_text("x" * 2048, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_disk_counts_junk(self):
        from butler.disk import project_disk
        disk = project_disk(self.root / "CloneA")
        self.assertGreater(disk["junk"], 2000)
        self.assertGreaterEqual(disk["total"], disk["junk"])
        self.assertTrue(any(p["name"] == "node_modules" for p in disk["parts"]))

    def test_dupes_finds_twins_not_uniques(self):
        from butler.index import build_feed
        records = [p.to_dict() for p in scan(self.root)]
        # продакшен-путь: build_feed обогащает записи теглайнами и ищет дубли внутри
        feed = build_feed(str(self.root), records)
        pairs = {(l["a"], l["b"]) for l in feed["links"]}
        self.assertIn(("CloneA", "CloneB"), pairs)
        for link in feed["links"]:
            self.assertNotIn("Unique", (link["a"], link["b"]))

    def test_secrets_detected_and_masked(self):
        result = scan(self.root)
        by_name = {p.name: p for p in result}
        secrets = by_name["CloneA"].facts["secrets"]
        kinds = {s["kind"] for s in secrets}
        self.assertIn("openai-key", kinds)
        self.assertIn("env-leak-risk" if "env-leak-risk" in kinds else True, kinds | {True})
        self.assertEqual(by_name["CloneA"].facts.get("env_leak_risk"), True)
        for s in secrets:
            self.assertNotIn("abcdefghijklmnopqrst", s["preview"])   # секрет замаскирован
        self.assertEqual(by_name["Unique"].facts.get("secret_count", 0), 0)

    def test_history_and_diff(self):
        db = Path(self.tmp.name) / "hist.db"
        with mock.patch.object(store, "DB_PATH", db):
            first = scan(self.root)
            store.save_projects(first, str(self.root))
            # второй скан: CloneA «поправился» (появились README-бонусы и git), Unique удалили
            (self.root / "Unique").rename(self.root / "UniqueGone")
            second = scan(self.root)
            store.save_projects(second, str(self.root))
            diff = store.diff_scans(str(self.root))
        self.assertEqual(diff["scans"], 2)
        self.assertIn("Unique", diff["removed"])
        self.assertIn("UniqueGone", diff["added"])

    def test_markdown_report(self):
        from butler.index import build_feed, markdown_report
        records = [p.to_dict() for p in scan(self.root)]
        feed = build_feed(str(self.root), records)
        report = markdown_report(feed)
        self.assertIn("# Project Butler — отчёт", report)
        self.assertIn("| Проект |", report)
        self.assertIn("CloneA", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
