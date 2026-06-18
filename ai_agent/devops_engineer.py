"""
DevOps Engineer — handles deployment, config, and infra tasks.
Reads Procfile, requirements.txt, app.py for context, calls the LLM.
"""

from pathlib import Path
from ai_agent import llm

ROLE = "devops"
KEYWORDS = [
    "deploy", "railway", "procfile", "gunicorn", "docker", "server",
    "cron", "vps", "env", "volume", "sqlite", "persistent", "startup",
    "log", "devops", "port", "health check",
]

_REPO_ROOT = Path(__file__).parent.parent
_CONFIG_FILES = ["Procfile", "requirements.txt"]
_MAX_FILE_CHARS = 3000


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
    app_src = _read("app.py")
    config_context = "\n\n".join(
        f"### {f}\n```\n{_read(f)}\n```" for f in _CONFIG_FILES
    )

    prompt = f"""You are a senior DevOps engineer. The app is a Flask/SQLite web app deployed on Railway via gunicorn.

## Task
{task['title']}

## Details
{task['body'].strip()}

## Config files
{config_context}

## app.py (relevant sections)
```python
{app_src}
```

## Instructions
Produce the minimal config or code change needed to complete the task.
Respond ONLY in this format — no extra prose:

## Summary
[one sentence describing what changes and why]

## Files to Change
- [list each file]

## Patch: [filename]
### Before
```
[exact original lines to replace — must match the file above verbatim, or "[new file]"]
```
### After
```
[replacement lines]
```

Repeat the Patch block for each file changed.
Keep changes as small as possible. Do not add unnecessary configuration.
"""
    return llm.call(prompt)
