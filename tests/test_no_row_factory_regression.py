"""Regression guard: forbid SQLite-only `.row_factory` assignment in live app code.

`connection.row_factory` is a sqlite3-only DBAPI extension. Assigning it on a
connection obtained from `db.connect()`/`db.get_connection()` silently breaks
in production (psycopg2 connections have no such attribute) — this is exactly
the bug that took down every `/contract/<id>` page after the 2026-07-10
Postgres cutover (see app.py contract_detail/contract_apply/opportunity_detail/
compare, fixed to use `get_engine()` + `text(...)` + `.mappings()` instead).

This test walks every .py file in the repo (excluding tests/ and vendored
dirs) and fails if a NEW `.row_factory` assignment shows up outside the
justified allowlist below.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# (relative file path, enclosing function-or-class name) pairs that are
# justified because the connection in scope is a raw `sqlite3.connect(...)`
# opened directly — NOT the DATABASE_URL-aware `db.connect()`/
# `db.get_connection()` helper — so `.row_factory` is guaranteed safe there
# regardless of which driver production is using.
JUSTIFIED = {
    ("db.py", "get_watchlist"),            # legacy watchlist table: sqlite3.connect(DB_PATH) directly
    ("ai_agent/memory.py", "RepoMemory"),  # self-contained AI-agent tool DB, always sqlite3.connect()
}

SKIP_DIR_PARTS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "tests",
    ".pytest_cache", ".ruff_cache", "static", "templates", "logs",
}


class _ScopeVisitor(ast.NodeVisitor):
    """Collect `.row_factory = ...` assignment lines with their enclosing
    function/class name stack, so justification can match on either.
    """

    def __init__(self):
        self.stack = []
        self.hits = []  # list of (lineno, tuple(scope_names))

    def _visit_scope(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._visit_scope(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_scope(node)

    def visit_ClassDef(self, node):
        self._visit_scope(node)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr == "row_factory":
                self.hits.append((node.lineno, tuple(self.stack)))
        self.generic_visit(node)


def _find_row_factory_assignments(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _ScopeVisitor()
    visitor.visit(tree)
    return visitor.hits


def test_no_unjustified_row_factory_assignment():
    offenders = []
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIR_PARTS for part in rel.parts):
            continue
        try:
            hits = _find_row_factory_assignments(path)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for lineno, scope in hits:
            rel_str = rel.as_posix()
            if any((rel_str, name) in JUSTIFIED for name in scope):
                continue
            offenders.append(f"{rel_str}:{lineno} (in {'.'.join(scope) or '<module>'})")

    assert not offenders, (
        "Unjustified `.row_factory` assignment found. This is a sqlite3-only "
        "API that breaks under psycopg2/production Postgres (AttributeError). "
        "Use db.get_engine() + sqlalchemy.text(...) + .mappings() instead, or "
        "add a justified (file, scope) entry to JUSTIFIED in this test if the "
        "connection is a verified raw sqlite3.connect():\n  "
        + "\n  ".join(offenders)
    )
