"""
Docs Writer — handles README and documentation tasks.
Reads existing docs for context, calls the LLM.
"""

from pathlib import Path
from ai_agent import llm

ROLE = "docs"
KEYWORDS = [
    "readme", "doc", "document", "comment", "explain", "instructions",
    "guide", "howto", "label", "description", "notes",
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
    readme = _read(_REPO_ROOT / "README.md")
    agent_readme = _read(_REPO_ROOT / "ai_agent" / "README.md")

    prompt = f"""You are a technical writer for a Python Flask web application called government-recompete-monitor.

## Task
{task['title']}

## Details
{task['body'].strip()}

## Existing README.md
```markdown
{readme}
```

## Existing ai_agent/README.md
```markdown
{agent_readme}
```

## Instructions
Write the documentation change needed to complete the task.
Respond ONLY in this format — no extra prose:

## Summary
[one sentence describing what changes and why]

## Files to Change
- [list each file]

## Patch: [filename]
### Before
```markdown
[exact original lines to replace, or "[new file]" if creating]
```
### After
```markdown
[replacement lines]
```

Be concise. Match the existing tone and style of the document.
"""
    return llm.call(prompt)
