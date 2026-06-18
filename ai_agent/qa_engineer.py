"""
QA Engineer agent — plans tests, assertions, and coverage tasks.
Returns a plan string. Does not edit files in this version.
"""

ROLE = "qa"
KEYWORDS = [
    "test", "qa", "assert", "pytest", "coverage", "unit", "integration",
    "fixture", "mock", "health", "smoke", "test_",
]


def can_handle(task: dict) -> bool:
    text = (task["title"] + task["body"]).lower()
    return any(kw in text for kw in KEYWORDS)


def plan(task: dict) -> str:
    """
    TODO: replace stub with Anthropic/OpenAI API call.

    Suggested prompt structure:
        f"You are a senior QA engineer working with pytest and Flask test client.
          Task: {task['title']}
          Details: {task['body']}
          Write a concise plan for the test file(s) to create or update.
          Name every test function and what it asserts. No code yet."
    """
    return (
        f"[QA STUB] Plan for: {task['title']}\n"
        "Steps would be generated here by the AI API.\n"
        "Files likely involved: tests/"
    )
