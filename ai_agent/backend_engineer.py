"""
Backend Engineer — handles Flask / SQLite / Python tasks.
Reads relevant source files, builds a prompt, calls the LLM.
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
_SOURCE_FILES = ["app.py", "db.py", "analytics.py", "views.py"]
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


def plan(task: dict) -> str:
    context = "\n\n".join(
        f"### {f}\n```python\n{_read(f)}\n```" for f in _SOURCE_FILES
    )

    prompt = f"""You are a senior Flask/SQLite backend engineer working on a government contract intelligence app.

## Task
{task['title']}

## Details
{task['body'].strip()}

## Relevant source files
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
[exact original lines to replace — must match the file above verbatim]
```
### After
```python
[replacement lines]
```

Repeat the Patch block for each file changed.
Keep changes as small as possible. Do not refactor unrelated code.
"""
    return llm.call(prompt)
