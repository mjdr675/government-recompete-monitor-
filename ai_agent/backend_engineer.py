"""
Backend Engineer agent — plans Python/Flask/SQLite tasks.
Returns a plan string. Does not edit files in this version.
"""

ROLE = "backend"
KEYWORDS = [
    "db.py", "app.py", "route", "sql", "sqlite", "endpoint",
    "filter", "query", "api", "ingest", "snapshot", "fts",
    "backend", "days_remaining", "get_contracts",
]


def can_handle(task: dict) -> bool:
    text = (task["title"] + task["body"]).lower()
    return any(kw in text for kw in KEYWORDS)


def plan(task: dict) -> str:
    """
    TODO: replace stub with Anthropic/OpenAI API call.

    Suggested prompt structure:
        f"You are a senior Flask/SQLite backend engineer.
          Task: {task['title']}
          Details: {task['body']}
          Write a concise step-by-step implementation plan.
          Name every file and function to change. No code yet."
    """
    return (
        f"[BACKEND STUB] Plan for: {task['title']}\n"
        "Steps would be generated here by the AI API.\n"
        "Files likely involved: db.py, app.py"
    )
