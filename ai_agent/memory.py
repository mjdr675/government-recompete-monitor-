"""
Repository Memory — SQLite-backed index of the Python codebase.

Extracts from every .py file:
  - functions (name, args, lineno, file)
  - classes (name, methods, lineno, file)
  - Flask routes (path, methods, handler, lineno, file)
  - imports (module, names, lineno, file)
  - templates referenced via render_template()

Auto-updates: compares file mtimes to stored values; only re-parses changed files.

Search API:
  mem.find_function("get_contracts")
  mem.find_route("/contracts")
  mem.find_import("flask")
  mem.find_template("contracts.html")
  mem.get_function_source("get_contracts")

CLI:
  python -m ai_agent.memory              # stats + update
  python -m ai_agent.memory --reindex    # force full reindex
"""

import ast
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_DB = REPO_ROOT / ".ai_agent_memory.db"

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY,
    path       TEXT    UNIQUE NOT NULL,
    mtime      REAL    NOT NULL,
    indexed_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS functions (
    id      INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name    TEXT    NOT NULL,
    lineno  INTEGER,
    args    TEXT
);

CREATE TABLE IF NOT EXISTS classes (
    id      INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name    TEXT    NOT NULL,
    lineno  INTEGER,
    methods TEXT
);

CREATE TABLE IF NOT EXISTS routes (
    id            INTEGER PRIMARY KEY,
    file_id       INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    path          TEXT    NOT NULL,
    methods       TEXT,
    function_name TEXT,
    lineno        INTEGER
);

CREATE TABLE IF NOT EXISTS imports (
    id      INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    module  TEXT    NOT NULL,
    names   TEXT,
    lineno  INTEGER
);

CREATE TABLE IF NOT EXISTS templates (
    id      INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name    TEXT    NOT NULL,
    lineno  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_fn_name       ON functions(name);
CREATE INDEX IF NOT EXISTS idx_route_path    ON routes(path);
CREATE INDEX IF NOT EXISTS idx_import_module ON imports(module);
CREATE INDEX IF NOT EXISTS idx_tmpl_name     ON templates(name);
"""


# ---------------------------------------------------------------------------
# AST parser
# ---------------------------------------------------------------------------

class _FileVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[dict] = []
        self.classes: list[dict] = []
        self.routes: list[dict] = []
        self.imports: list[dict] = []
        self.templates: list[dict] = []
        self._class_depth = 0

    # -- imports -------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({"module": alias.name, "names": None, "lineno": node.lineno})

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            names = ",".join(a.name for a in node.names)
            self.imports.append({"module": node.module, "names": names, "lineno": node.lineno})

    # -- classes -------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        methods = [
            item.name for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.classes.append({"name": node.name, "lineno": node.lineno, "methods": methods})
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    # -- functions + routes -------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for dec in node.decorator_list:
            route = self._extract_route(dec, node.name, node.lineno)
            if route:
                self.routes.append(route)

        if self._class_depth == 0:
            args = [a.arg for a in node.args.args]
            self.functions.append({"name": node.name, "lineno": node.lineno, "args": args})

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def _extract_route(self, dec: ast.expr, func_name: str, lineno: int) -> dict | None:
        if not isinstance(dec, ast.Call):
            return None
        func = dec.func
        if not (isinstance(func, ast.Attribute) and func.attr == "route"):
            return None
        if not dec.args:
            return None
        first = dec.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            return None
        path = first.value
        http_methods = "GET"
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, ast.List):
                elts = [
                    e.value for e in kw.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                ]
                http_methods = ",".join(elts)
        return {"path": path, "methods": http_methods, "function_name": func_name, "lineno": lineno}

    # -- template references ------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        is_render = (
            (isinstance(func, ast.Name) and func.id == "render_template") or
            (isinstance(func, ast.Attribute) and func.attr == "render_template")
        )
        if is_render and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                self.templates.append({"name": first.value, "lineno": node.lineno})
        self.generic_visit(node)


def _parse_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return {"functions": [], "classes": [], "routes": [], "imports": [], "templates": []}
    visitor = _FileVisitor()
    visitor.visit(tree)
    return {
        "functions": visitor.functions,
        "classes":   visitor.classes,
        "routes":    visitor.routes,
        "imports":   visitor.imports,
        "templates": visitor.templates,
    }


# ---------------------------------------------------------------------------
# Repository Memory
# ---------------------------------------------------------------------------

class RepoMemory:
    def __init__(self, repo_root: Path = REPO_ROOT, db_path: Path = DEFAULT_DB) -> None:
        self.repo_root = repo_root
        self.db_path = db_path
        self._con = sqlite3.connect(str(db_path))
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_SCHEMA)
        self._con.commit()

    # -- file discovery -----------------------------------------------

    def _py_files(self) -> list[Path]:
        skip = {".git", "__pycache__", ".venv", "venv", "node_modules"}
        result = []
        for p in self.repo_root.rglob("*.py"):
            if any(part in skip for part in p.parts):
                continue
            result.append(p)
        return sorted(result)

    # -- indexing -------------------------------------------------------

    def _stored_mtime(self, rel: str) -> float | None:
        row = self._con.execute("SELECT mtime FROM files WHERE path=?", (rel,)).fetchone()
        return row["mtime"] if row else None

    def _delete_file(self, rel: str) -> None:
        self._con.execute("DELETE FROM files WHERE path=?", (rel,))

    def _index_file(self, path: Path) -> None:
        rel = str(path.relative_to(self.repo_root))
        mtime = path.stat().st_mtime
        now = datetime.now(timezone.utc).isoformat()

        self._delete_file(rel)
        self._con.execute(
            "INSERT INTO files(path, mtime, indexed_at) VALUES(?,?,?)",
            (rel, mtime, now)
        )
        file_id = self._con.execute("SELECT id FROM files WHERE path=?", (rel,)).fetchone()["id"]

        parsed = _parse_file(path)

        for fn in parsed["functions"]:
            self._con.execute(
                "INSERT INTO functions(file_id,name,lineno,args) VALUES(?,?,?,?)",
                (file_id, fn["name"], fn["lineno"], json.dumps(fn["args"]))
            )
        for cls in parsed["classes"]:
            self._con.execute(
                "INSERT INTO classes(file_id,name,lineno,methods) VALUES(?,?,?,?)",
                (file_id, cls["name"], cls["lineno"], json.dumps(cls["methods"]))
            )
        for r in parsed["routes"]:
            self._con.execute(
                "INSERT INTO routes(file_id,path,methods,function_name,lineno) VALUES(?,?,?,?,?)",
                (file_id, r["path"], r["methods"], r["function_name"], r["lineno"])
            )
        for imp in parsed["imports"]:
            self._con.execute(
                "INSERT INTO imports(file_id,module,names,lineno) VALUES(?,?,?,?)",
                (file_id, imp["module"], imp["names"], imp["lineno"])
            )
        for tmpl in parsed["templates"]:
            self._con.execute(
                "INSERT INTO templates(file_id,name,lineno) VALUES(?,?,?)",
                (file_id, tmpl["name"], tmpl["lineno"])
            )

    def index(self, force: bool = False) -> dict:
        """Index all Python files. With force=True, re-index even unchanged files."""
        files = self._py_files()
        indexed = skipped = 0
        for path in files:
            rel = str(path.relative_to(self.repo_root))
            mtime = path.stat().st_mtime
            if not force and self._stored_mtime(rel) == mtime:
                skipped += 1
                continue
            self._index_file(path)
            indexed += 1

        # Remove entries for deleted files
        stored_paths = {r["path"] for r in self._con.execute("SELECT path FROM files").fetchall()}
        current_rels = {str(p.relative_to(self.repo_root)) for p in files}
        for stale in stored_paths - current_rels:
            self._delete_file(stale)

        self._con.commit()
        return {"indexed": indexed, "skipped": skipped, "total": len(files)}

    def update(self) -> dict:
        """Re-index only files whose mtime has changed."""
        return self.index(force=False)

    # -- search API ----------------------------------------------------

    def find_function(self, name: str) -> list[dict]:
        """Find functions by exact name. Returns list of matches across all files."""
        rows = self._con.execute(
            "SELECT f.name, f.lineno, f.args, fi.path "
            "FROM functions f JOIN files fi ON f.file_id=fi.id "
            "WHERE f.name=? ORDER BY fi.path, f.lineno",
            (name,)
        ).fetchall()
        return [
            {"name": r["name"], "lineno": r["lineno"],
             "args": json.loads(r["args"] or "[]"), "file": r["path"]}
            for r in rows
        ]

    def find_route(self, path: str) -> list[dict]:
        """Find Flask routes by path (exact or partial match)."""
        rows = self._con.execute(
            "SELECT r.path, r.methods, r.function_name, r.lineno, fi.path as file "
            "FROM routes r JOIN files fi ON r.file_id=fi.id "
            "WHERE r.path=? OR r.path LIKE ? ORDER BY r.path",
            (path, f"%{path}%")
        ).fetchall()
        return [
            {"path": r["path"], "methods": r["methods"],
             "function_name": r["function_name"], "lineno": r["lineno"], "file": r["file"]}
            for r in rows
        ]

    def find_import(self, module: str) -> list[dict]:
        """Find all files that import a module (exact or prefix match)."""
        rows = self._con.execute(
            "SELECT i.module, i.names, i.lineno, fi.path "
            "FROM imports i JOIN files fi ON i.file_id=fi.id "
            "WHERE i.module=? OR i.module LIKE ? ORDER BY fi.path",
            (module, f"{module}.%")
        ).fetchall()
        return [
            {"module": r["module"], "names": r["names"],
             "lineno": r["lineno"], "file": r["path"]}
            for r in rows
        ]

    def find_template(self, name: str) -> list[dict]:
        """Find all places where a template is rendered."""
        rows = self._con.execute(
            "SELECT t.name, t.lineno, fi.path "
            "FROM templates t JOIN files fi ON t.file_id=fi.id "
            "WHERE t.name=? OR t.name LIKE ? ORDER BY fi.path",
            (name, f"%{name}%")
        ).fetchall()
        return [{"name": r["name"], "lineno": r["lineno"], "file": r["path"]} for r in rows]

    def find_class(self, name: str) -> list[dict]:
        rows = self._con.execute(
            "SELECT c.name, c.lineno, c.methods, fi.path "
            "FROM classes c JOIN files fi ON c.file_id=fi.id "
            "WHERE c.name=? ORDER BY fi.path",
            (name,)
        ).fetchall()
        return [
            {"name": r["name"], "lineno": r["lineno"],
             "methods": json.loads(r["methods"] or "[]"), "file": r["path"]}
            for r in rows
        ]

    # -- source extraction --------------------------------------------

    def get_function_source(self, name: str) -> str | None:
        """
        Return the source code of the first function matching `name`.
        Reads only the containing file; extracts only that function via AST.
        """
        matches = self.find_function(name)
        if not matches:
            return None
        path = self.repo_root / matches[0]["file"]
        if not path.exists():
            return None
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.get_source_segment(source, node)
        return None

    # -- stats ---------------------------------------------------------

    def stats(self) -> dict:
        def count(table: str) -> int:
            return self._con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {
            "files":     count("files"),
            "functions": count("functions"),
            "classes":   count("classes"),
            "routes":    count("routes"),
            "imports":   count("imports"),
            "templates": count("templates"),
        }

    def close(self) -> None:
        self._con.close()


# ---------------------------------------------------------------------------
# Singleton accessor for use across the agent system
# ---------------------------------------------------------------------------

_instance: RepoMemory | None = None


def get_memory(repo_root: Path = REPO_ROOT) -> RepoMemory:
    global _instance
    if _instance is None:
        _instance = RepoMemory(repo_root=repo_root)
    return _instance


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    force = "--reindex" in sys.argv
    mem = get_memory()
    result = mem.index(force=force)
    s = mem.stats()
    print(f"Indexed : {result['indexed']} files  |  Skipped (unchanged): {result['skipped']}")
    print(f"DB stats: {s['files']} files | {s['functions']} functions | "
          f"{s['classes']} classes | {s['routes']} routes | "
          f"{s['imports']} imports | {s['templates']} template refs")
    mem.close()
