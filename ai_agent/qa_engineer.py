"""
QA Engineer — handles pytest test writing tasks.
Reads app.py and existing tests for context, calls the LLM.
"""

from pathlib import Path
from ai_agent import llm

ROLE = "qa"
KEYWORDS = [
    "test", "qa", "assert", "pytest", "coverage", "unit", "integration",
    "fixture", "mock", "health", "smoke", "test_",
]

_REPO_ROOT = Path(__file__).parent.parent
_MAX_FILE_CHARS = 4000


def can_handle(task: dict) -> bool:
    text = (task["title"] + task["body"]).lower()
    return any(kw in text for kw in KEYWORDS)


def _read(path: Path) -> str:
    if not path.exists():
        return f"[not found: {path.name}]"
    text = path.read_text()
    if len(text) > _MAX_FILE_CHARS:
        text = text[:_MAX_FILE_CHARS] + f"\n... [{len(text) - _MAX_FILE_CHARS} chars truncated]"
    return text


def plan(task: dict, memory=None) -> str:
    tests_dir = _REPO_ROOT / "tests"
    existing_tests = ""
    if tests_dir.exists():
        files = list(tests_dir.glob("test_*.py"))
        existing_tests = "\n\n".join(
            f"### {f.name}\n```python\n{_read(f)}\n```" for f in files
        )
    else:
        existing_tests = "[No tests/ directory exists yet — create it]"

    app_src = _read(_REPO_ROOT / "app.py")

    prompt = f"""You are a senior QA engineer. You write pytest tests for a Flask application.
Use Flask's built-in test client (app.test_client()) — no mocking of the database.

## Task
{task['title']}

## Details
{task['body'].strip()}

## app.py (source under test)
```python
{app_src}
```

## Existing tests
{existing_tests}

## Instructions
Write the test file(s) needed to complete the task above.
Respond ONLY in this format — no extra prose:

## Summary
[one sentence describing what the tests verify]

## Files to Change
- [list each file, e.g. tests/test_health.py]

## Patch: [filename]
### Before
```python
[exact original lines to replace, or "[new file]" if creating]
```
### After
```python
[complete new file content or replacement lines]
```

Keep tests minimal and focused. Each test function tests one thing.
"""
    return llm.call(prompt)
