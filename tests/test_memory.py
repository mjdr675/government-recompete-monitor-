"""
Tests for ai_agent/memory.py — repository knowledge base.
Uses a temp directory with synthetic Python files so tests are isolated
from actual repo state and run fast.
"""

import json
import textwrap
import time
from pathlib import Path

import pytest

from ai_agent.memory import RepoMemory, _parse_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo with a few Python source files."""
    app = tmp_path / "app.py"
    app.write_text(textwrap.dedent("""\
        from flask import Flask, render_template, request
        from db import get_contracts

        app = Flask(__name__)

        @app.route("/")
        def index():
            return render_template("dashboard.html")

        @app.route("/items", methods=["GET", "POST"])
        def items():
            return render_template("items.html", data=[])

        @app.route("/item/<int:item_id>")
        def item_detail(item_id):
            return render_template("detail.html")

        if __name__ == "__main__":
            app.run()
    """))

    db = tmp_path / "db.py"
    db.write_text(textwrap.dedent("""\
        import sqlite3
        import json

        DB_PATH = "app.db"

        class QueryBuilder:
            def __init__(self, table):
                self.table = table

            def build(self):
                return f"SELECT * FROM {self.table}"

        def connect():
            return sqlite3.connect(DB_PATH)

        def get_contracts(q="", limit=25):
            conn = connect()
            return conn.execute("SELECT * FROM contracts LIMIT ?", [limit]).fetchall()

        def upsert_contract(row):
            pass
    """))

    utils = tmp_path / "utils.py"
    utils.write_text(textwrap.dedent("""\
        from datetime import date, timezone
        import os

        def today_iso():
            return date.today().isoformat()

        def env_or(key, default=""):
            return os.environ.get(key, default)
    """))

    return tmp_path


@pytest.fixture()
def mem(repo: Path, tmp_path: Path) -> RepoMemory:
    db_path = tmp_path / "test_memory.db"
    m = RepoMemory(repo_root=repo, db_path=db_path)
    m.index(force=True)
    return m


# ---------------------------------------------------------------------------
# Parser unit tests (no DB)
# ---------------------------------------------------------------------------

class TestParseFile:
    def test_functions(self, repo: Path) -> None:
        parsed = _parse_file(repo / "db.py")
        names = [f["name"] for f in parsed["functions"]]
        assert "connect" in names
        assert "get_contracts" in names
        assert "upsert_contract" in names

    def test_function_args(self, repo: Path) -> None:
        parsed = _parse_file(repo / "db.py")
        fn = next(f for f in parsed["functions"] if f["name"] == "get_contracts")
        assert "q" in fn["args"]
        assert "limit" in fn["args"]

    def test_class_detected(self, repo: Path) -> None:
        parsed = _parse_file(repo / "db.py")
        assert any(c["name"] == "QueryBuilder" for c in parsed["classes"])

    def test_class_methods(self, repo: Path) -> None:
        parsed = _parse_file(repo / "db.py")
        cls = next(c for c in parsed["classes"] if c["name"] == "QueryBuilder")
        assert "build" in cls["methods"]
        assert "__init__" in cls["methods"]

    def test_methods_not_in_functions(self, repo: Path) -> None:
        parsed = _parse_file(repo / "db.py")
        fn_names = [f["name"] for f in parsed["functions"]]
        assert "build" not in fn_names
        assert "__init__" not in fn_names

    def test_flask_routes(self, repo: Path) -> None:
        parsed = _parse_file(repo / "app.py")
        paths = [r["path"] for r in parsed["routes"]]
        assert "/" in paths
        assert "/items" in paths
        assert "/item/<int:item_id>" in paths

    def test_route_methods(self, repo: Path) -> None:
        parsed = _parse_file(repo / "app.py")
        items_route = next(r for r in parsed["routes"] if r["path"] == "/items")
        assert "GET" in items_route["methods"]
        assert "POST" in items_route["methods"]

    def test_route_default_method(self, repo: Path) -> None:
        parsed = _parse_file(repo / "app.py")
        root = next(r for r in parsed["routes"] if r["path"] == "/")
        assert root["methods"] == "GET"

    def test_route_handler_name(self, repo: Path) -> None:
        parsed = _parse_file(repo / "app.py")
        root = next(r for r in parsed["routes"] if r["path"] == "/")
        assert root["function_name"] == "index"

    def test_imports(self, repo: Path) -> None:
        parsed = _parse_file(repo / "app.py")
        modules = [i["module"] for i in parsed["imports"]]
        assert "flask" in modules
        assert "db" in modules

    def test_import_names(self, repo: Path) -> None:
        parsed = _parse_file(repo / "app.py")
        flask_imp = next(i for i in parsed["imports"] if i["module"] == "flask")
        assert "Flask" in flask_imp["names"]
        assert "render_template" in flask_imp["names"]

    def test_templates(self, repo: Path) -> None:
        parsed = _parse_file(repo / "app.py")
        names = [t["name"] for t in parsed["templates"]]
        assert "dashboard.html" in names
        assert "items.html" in names
        assert "detail.html" in names

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(\n")
        parsed = _parse_file(bad)
        assert parsed["functions"] == []
        assert parsed["routes"] == []


# ---------------------------------------------------------------------------
# Search API tests (via DB)
# ---------------------------------------------------------------------------

class TestSearchAPI:
    def test_find_function_exact(self, mem: RepoMemory) -> None:
        results = mem.find_function("get_contracts")
        assert len(results) == 1
        assert results[0]["file"].endswith("db.py")

    def test_find_function_args(self, mem: RepoMemory) -> None:
        results = mem.find_function("get_contracts")
        assert "q" in results[0]["args"]
        assert "limit" in results[0]["args"]

    def test_find_function_not_found(self, mem: RepoMemory) -> None:
        assert mem.find_function("nonexistent_xyz") == []

    def test_find_route_exact(self, mem: RepoMemory) -> None:
        results = mem.find_route("/items")
        assert any(r["path"] == "/items" for r in results)

    def test_find_route_partial(self, mem: RepoMemory) -> None:
        results = mem.find_route("item")
        paths = [r["path"] for r in results]
        assert "/items" in paths or "/item/<int:item_id>" in paths

    def test_find_route_handler(self, mem: RepoMemory) -> None:
        results = mem.find_route("/")
        assert results[0]["function_name"] == "index"

    def test_find_import_exact(self, mem: RepoMemory) -> None:
        results = mem.find_import("flask")
        assert len(results) == 1
        assert "Flask" in results[0]["names"]

    def test_find_import_prefix(self, mem: RepoMemory) -> None:
        results = mem.find_import("datetime")
        assert any(r["module"].startswith("datetime") for r in results)

    def test_find_template_exact(self, mem: RepoMemory) -> None:
        results = mem.find_template("dashboard.html")
        assert len(results) == 1
        assert results[0]["file"].endswith("app.py")

    def test_find_template_partial(self, mem: RepoMemory) -> None:
        results = mem.find_template(".html")
        assert len(results) >= 3

    def test_find_class(self, mem: RepoMemory) -> None:
        results = mem.find_class("QueryBuilder")
        assert len(results) == 1
        assert "build" in results[0]["methods"]

    def test_get_function_source(self, mem: RepoMemory) -> None:
        src = mem.get_function_source("today_iso")
        assert src is not None
        assert "def today_iso" in src
        assert "date.today()" in src

    def test_get_function_source_not_found(self, mem: RepoMemory) -> None:
        assert mem.get_function_source("does_not_exist") is None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_counts(self, mem: RepoMemory) -> None:
        s = mem.stats()
        assert s["files"] == 3
        assert s["functions"] >= 4
        assert s["routes"] == 3
        assert s["classes"] == 1
        assert s["templates"] == 3

    def test_stats_keys(self, mem: RepoMemory) -> None:
        keys = mem.stats().keys()
        assert {"files", "functions", "classes", "routes", "imports", "templates"} == set(keys)


# ---------------------------------------------------------------------------
# Auto-update (mtime-based)
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_skips_unchanged(self, mem: RepoMemory, repo: Path) -> None:
        result = mem.update()
        assert result["indexed"] == 0
        assert result["skipped"] == 3

    def test_reindexes_changed_file(self, mem: RepoMemory, repo: Path) -> None:
        utils = repo / "utils.py"
        # Add a new function
        time.sleep(0.05)  # ensure mtime differs
        utils.write_text(utils.read_text() + "\ndef new_helper():\n    pass\n")
        # Touch mtime explicitly
        path = Path(utils)
        path.touch()

        result = mem.update()
        assert result["indexed"] == 1

        fns = mem.find_function("new_helper")
        assert len(fns) == 1

    def test_removes_deleted_file(self, mem: RepoMemory, repo: Path) -> None:
        (repo / "utils.py").unlink()
        mem.update()
        assert mem.find_function("today_iso") == []

    def test_force_reindex_all(self, mem: RepoMemory) -> None:
        result = mem.index(force=True)
        assert result["indexed"] == 3
        assert result["skipped"] == 0
