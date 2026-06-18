"""
Frontend Engineer — handles Jinja2 template and HTML tasks.
Reads templates directory, builds a prompt, calls the LLM.
"""

from pathlib import Path
from ai_agent import llm

ROLE = "frontend"
KEYWORDS = [
    "template", "html", "jinja", "css", "ui", "label", "frontend",
    "views.html", "contracts.html", "dashboard.html", "pagination",
    "display", "render", "layout", "base.html",
]

_REPO_ROOT = Path(__file__).parent.parent
_MAX_FILE_CHARS = 3000


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


def _relevant_templates(task: dict) -> list[Path]:
    templates_dir = _REPO_ROOT / "templates"
    all_templates = sorted(templates_dir.glob("*.html"))
    # Always include any template named in the task body
    task_text = (task["title"] + task["body"]).lower()
    relevant = [t for t in all_templates if t.name.lower() in task_text]
    # Fall back to all templates if none matched by name
    return relevant if relevant else all_templates


def plan(task: dict) -> str:
    templates = _relevant_templates(task)
    context = "\n\n".join(
        f"### templates/{t.name}\n```html\n{_read(t)}\n```" for t in templates
    )

    prompt = f"""You are a senior frontend engineer working with Jinja2 templates and plain HTML.
The app has no JavaScript framework — only server-rendered HTML with Jinja2.

## Task
{task['title']}

## Details
{task['body'].strip()}

## Relevant templates
{context}

## Instructions
Produce a minimal, safe template change that completes the task above.
Respond ONLY in this format — no extra prose:

## Summary
[one sentence describing what changes and why]

## Files to Change
- [list each file]

## Patch: [filename]
### Before
```html
[exact original lines to replace — must match the file above verbatim]
```
### After
```html
[replacement lines]
```

Repeat the Patch block for each file changed.
Keep changes as small as possible. Do not redesign the page.
"""
    return llm.call(prompt)
