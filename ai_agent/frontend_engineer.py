"""
Frontend Engineer agent — plans Jinja2 template and HTML/CSS tasks.
Returns a plan string. Does not edit files in this version.
"""

ROLE = "frontend"
KEYWORDS = [
    "template", "html", "jinja", "css", "ui", "label", "frontend",
    "views.html", "contracts.html", "dashboard.html", "pagination",
    "display", "render", "layout", "base.html",
]


def can_handle(task: dict) -> bool:
    text = (task["title"] + task["body"]).lower()
    return any(kw in text for kw in KEYWORDS)


def plan(task: dict) -> str:
    """
    TODO: replace stub with Anthropic/OpenAI API call.

    Suggested prompt structure:
        f"You are a senior frontend engineer working with Jinja2 and plain HTML.
          Task: {task['title']}
          Details: {task['body']}
          Write a concise step-by-step implementation plan.
          Name every template file and block to change. No code yet."
    """
    return (
        f"[FRONTEND STUB] Plan for: {task['title']}\n"
        "Steps would be generated here by the AI API.\n"
        "Files likely involved: templates/"
    )
