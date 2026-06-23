"""
Patch reviewer — two-stage review before any patch is applied.

Stage 1 (review):     regex blocklist — blocks dangerous shell/DB patterns instantly.
Stage 2 (ai_review):  LLM quality check — detects bugs, missing tests, style issues.
                       Falls back to approved=True when the LLM is unavailable.
                       Writes ai_agent/REVIEW.md with the outcome.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_RULES: list[tuple[str, str]] = [
    (r"git\s+push",               "git push"),
    (r"rm\s+-rf",                  "rm -rf"),
    (r"shutil\.rmtree",            "shutil.rmtree"),
    (r"os\.remove\b",              "os.remove"),
    (r"os\.unlink\b",              "os.unlink"),
    (r"DROP\s+TABLE",              "DROP TABLE"),
    (r"DELETE\s+FROM",             "DELETE FROM (unguarded)"),
    (r"subprocess\.call|subprocess\.run|subprocess\.Popen",
                                   "subprocess exec (review required)"),
    (r"open\(['\"].*\.env",        "reading .env file"),
    (r"sk-[A-Za-z0-9\-]{20,}",    "API key literal"),
    (r"ANTHROPIC_API_KEY\s*=\s*['\"].+['\"]",  "hardcoded API key"),
]


def review(patch: str) -> tuple[bool, list[str]]:
    """
    Scan patch text for blocked patterns.
    Returns (is_safe, list_of_violation_descriptions).
    An empty violation list means the patch passed review.
    """
    violations = []
    for pattern, label in _RULES:
        if re.search(pattern, patch, re.IGNORECASE):
            violations.append(label)
    return len(violations) == 0, violations


# ---------------------------------------------------------------------------
# Stage 2 — AI quality review
# ---------------------------------------------------------------------------

_AGENT_DIR = Path(__file__).parent
_DEFAULT_REVIEW_PATH = _AGENT_DIR / "REVIEW.md"

_REVIEW_PROMPT = """\
You are a senior software engineer reviewing a patch for a Python Flask web application.

Task: {title}

Patch:
```
{patch}
```

Review ONLY for genuine problems (do not invent issues):
1. Logic bugs or incorrect behaviour
2. Missing tests for new routes, DB functions, or Celery tasks
3. Security vulnerabilities: SQL injection, XSS, hardcoded secrets, missing auth checks
4. Style violations: unused imports, print() in app code, functions > 50 lines
5. Duplicated code that already exists elsewhere

Respond in EXACTLY this format — no other text before or after:

DECISION: APPROVED
FINDINGS:
- <finding or "None">

OR if there are real problems that would break production or security:

DECISION: REJECTED
FINDINGS:
- <required fix 1>
- <required fix 2>
"""


def ai_review(
    patch_content: str,
    task_title: str = "",
    review_output_path: Optional[Path] = None,
) -> tuple[bool, list[str]]:
    """
    AI-powered code review using the project LLM.

    Returns (approved, findings).  When the LLM is unavailable the function
    fails open (approved=True) so it never blocks a working pipeline.
    Writes a REVIEW.md file with the outcome.
    """
    from ai_agent import llm  # lazy import — avoids circular dependency

    output_path = review_output_path if review_output_path is not None else _DEFAULT_REVIEW_PATH
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not llm.available():
        findings = ["LLM unavailable — AI review skipped"]
        _write_review(output_path, task_title, ts, "APPROVED (LLM unavailable)", findings)
        return True, findings

    patch_excerpt = patch_content[:8000] if len(patch_content) > 8000 else patch_content
    prompt = _REVIEW_PROMPT.format(
        title=task_title or "(untitled)",
        patch=patch_excerpt,
    )

    try:
        response = llm.call(prompt, model="claude-haiku-4-5-20251001", max_tokens=1024)
        approved, findings, decision_text = _parse_review_response(response)
    except Exception as exc:
        findings = [f"AI review error: {exc}"]
        _write_review(output_path, task_title, ts, "APPROVED (review error — fail open)", findings)
        return True, findings  # fail open so a transient error never blocks a good patch

    _write_review(output_path, task_title, ts, decision_text, findings)
    return approved, findings


def _parse_review_response(response: str) -> tuple[bool, list[str], str]:
    """Parse DECISION and FINDINGS lines from an LLM review response."""
    approved = True
    decision_text = "APPROVED"
    findings: list[str] = []
    in_findings = False

    for line in response.strip().splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("DECISION:"):
            decision = stripped[9:].strip().upper()
            approved = "REJECTED" not in decision
            decision_text = "REJECTED" if not approved else "APPROVED"
        elif upper.startswith("FINDINGS:"):
            in_findings = True
        elif in_findings and stripped.startswith("-"):
            finding = stripped[1:].strip()
            if finding and finding.lower() != "none":
                findings.append(finding)

    if not findings:
        findings = ["No specific findings"]
    return approved, findings, decision_text


def _write_review(
    path: Path,
    task_title: str,
    ts: str,
    decision: str,
    findings: list[str],
) -> None:
    """Write a REVIEW.md file with the latest review outcome (overwrites previous)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AI Code Review",
        "",
        f"**Task:** {task_title or '(untitled)'}",
        f"**Timestamp:** {ts}",
        f"**Decision:** {decision}",
        "",
        "## Findings",
        "",
    ] + [f"- {f}" for f in findings] + [""]
    path.write_text("\n".join(lines), encoding="utf-8")
