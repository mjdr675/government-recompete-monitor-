"""
Backend Engineer — handles Flask / SQLite / Python tasks.

Uses RepoMemory to find specific functions and read only what's relevant,
rather than dumping entire files into the prompt.
Falls back to full-file reads when memory is unavailable.
"""

from pathlib import Path
from ai_agent import llm

ROLE = "backend"
KEYWORDS = [
    "db.py", "app.py", "route", "sql", "sqlite", "endpoint",
    "filter", "query", "api", "ingest", "snapshot", "fts",
    "backend", "days_remaining", "get_contracts",
]

_REPO_ROOT = Path(__file__).parent.parent
_MAX_FILE_CHARS = 4000


def can_handle(task: dict) -> bool:
    text = (task["title"] + task["body"]).lower()
    return any(kw in text for kw in KEYWORDS)


def _read(filename: str) -> str:
    path = _REPO_ROOT / filename
    if not path.exists():
        return f"[not found: {filename}]"
    text = path.read_text()
    if len(text) > _MAX_FILE_CHARS:
        text = text[:_MAX_FILE_CHARS] + f"\n... [{len(text) - _MAX_FILE_CHARS} chars truncated]"
    return text


def _build_context(task: dict, memory) -> str:
    """
    Use memory index to fetch targeted context:
    - Functions mentioned by name in the task body
    - Routes mentioned in the task body
    - Falls back to full db.py + app.py if nothing specific is found
    """
    if memory is None:
        return (
            f"### app.py\n```python\n{_read('app.py')}\n```\n\n"
            f"### db.py\n```python\n{_read('db.py')}\n```"
        )

    sections: list[str] = []
    task_text = (task["title"] + " " + task["body"]).lower()

    # Targeted: pull source for any known function mentioned in task text
    found_fns: set[str] = set()
    all_fns = memory._con.execute("SELECT name FROM functions").fetchall()
    for row in all_fns:
        name = row[0]
        if name in task_text and name not in found_fns:
            src = memory.get_function_source(name)
            if src:
                loc = memory.find_function(name)
                file_ref = loc[0]["file"] if loc else "?"
                sections.append(f"### {name}() in {file_ref}\n```python\n{src}\n```")
                found_fns.add(name)

    # Include all routes from the index (compact — not full file)
    routes = memory.find_route("/")
    if routes:
        route_lines = "\n".join(
            f"  {r['path']} [{r['methods']}] -> {r['function_name']}() in {r['file']}"
            for r in routes
        )
        sections.append(f"### Flask routes (from index)\n```\n{route_lines}\n```")

    # If nothing relevant found via index, fall back to full files
    if not sections:
        sections = [
            f"### app.py\n```python\n{_read('app.py')}\n```",
            f"### db.py\n```python\n{_read('db.py')}\n```",
        ]

    return "\n\n".join(sections)


def plan(task: dict, memory=None) -> str:
    context = _build_context(task, memory)

    prompt = f"""You are a senior Flask/SQLite backend engineer working on a government contract intelligence app.

## Task
{task['title']}

## Details
{task['body'].strip()}

## Relevant code (from repository index)
{context}

## Instructions
Produce a minimal, safe code change that completes the task above.
Respond ONLY in this format — no extra prose:

## Summary
[one sentence describing what changes and why]

## Files to Change
- [list each file]

## Patch: [filename]
### Before
```python
[exact original lines to replace — must match the file verbatim]
```
### After
```python
[replacement lines]
```

Repeat the Patch block for each file changed.
Keep changes as small as possible. Do not refactor unrelated code.
"""
    return llm.call(prompt)
