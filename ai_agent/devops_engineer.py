"""
DevOps Engineer agent — plans deployment, infra, and config tasks.
Returns a plan string. Does not edit files in this version.
"""

ROLE = "devops"
KEYWORDS = [
    "deploy", "railway", "procfile", "gunicorn", "docker", "server",
    "cron", "vps", "env", "volume", "sqlite", "persistent", "startup",
    "log", "devops", "port", "health check",
]


def can_handle(task: dict) -> bool:
    text = (task["title"] + task["body"]).lower()
    return any(kw in text for kw in KEYWORDS)


def plan(task: dict) -> str:
    """
    TODO: replace stub with Anthropic/OpenAI API call.

    Suggested prompt structure:
        f"You are a senior DevOps engineer familiar with Railway, gunicorn, and Linux VPS.
          Task: {task['title']}
          Details: {task['body']}
          Write a concise step-by-step plan.
          Name every file and config change needed. No code yet."
    """
    return (
        f"[DEVOPS STUB] Plan for: {task['title']}\n"
        "Steps would be generated here by the AI API.\n"
        "Files likely involved: Procfile, railway.json, app.py"
    )
