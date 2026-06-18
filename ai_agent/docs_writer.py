"""
Docs Writer agent — plans README, docstring, and documentation tasks.
Returns a plan string. Does not edit files in this version.
"""

ROLE = "docs"
KEYWORDS = [
    "readme", "doc", "document", "comment", "explain", "instructions",
    "guide", "howto", "label", "description", "notes",
]


def can_handle(task: dict) -> bool:
    text = (task["title"] + task["body"]).lower()
    return any(kw in text for kw in KEYWORDS)


def plan(task: dict) -> str:
    """
    TODO: replace stub with Anthropic/OpenAI API call.

    Suggested prompt structure:
        f"You are a technical writer for a Python web application.
          Task: {task['title']}
          Details: {task['body']}
          Write a concise plan for what to document and where.
          Name every file and section to update. No writing yet."
    """
    return (
        f"[DOCS STUB] Plan for: {task['title']}\n"
        "Steps would be generated here by the AI API.\n"
        "Files likely involved: README.md, ai_agent/README.md"
    )
