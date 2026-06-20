"""
Human escalation — proactive safety checks for the autonomous loop.

Three escalation triggers:
  AMBIGUOUS_TASK    — task body is too vague to implement safely
  REPEATED_FAILURES — same or related tasks failing repeatedly
  RISKY_CODE        — patch touches paths requiring a human sign-off

Usage:
  from ai_agent.escalation import (
      check_task_ambiguity,
      check_repeated_failures,
      check_risky_code,
      write_escalation_report,
      should_escalate,
  )

  triggers = []
  t = check_task_ambiguity(task)
  if t: triggers.append(t)

  t = check_risky_code(patch_content, task_filename="052-daemon-mode.md")
  if t: triggers.append(t)

  if should_escalate(triggers):
      write_escalation_report(triggers, path=ESCALATE_PATH)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_AGENT_DIR = Path(__file__).parent
DEFAULT_ESCALATE_PATH = _AGENT_DIR / "ESCALATE.md"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

AMBIGUOUS_TASK = "ambiguous_task"
REPEATED_FAILURES = "repeated_failures"
RISKY_CODE = "risky_code"


@dataclass
class EscalationTrigger:
    reason: str           # one of the three constants above
    message: str          # one-line human-readable summary
    task_filename: str    # which task triggered this (may be empty)
    details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ambiguity detection
# ---------------------------------------------------------------------------

_VAGUE_ONLY = re.compile(
    r"^\s*(?:improve|enhance|fix|update|refactor|clean|optimise|optimize"
    r"|make\s+better|make\s+it\s+(?:work|good|fast)|add\s+things?|do\s+(?:it|stuff|things))"
    r"[\s.!]*$",
    re.IGNORECASE,
)

_MIN_BODY_LENGTH = 30          # chars of actual content (stripped)
_MIN_REQUIREMENT_WORDS = 5     # at minimum five words of instruction


def check_task_ambiguity(
    task: dict,
    min_body_length: int = _MIN_BODY_LENGTH,
) -> Optional[EscalationTrigger]:
    """
    Return an :class:`EscalationTrigger` when the task body is too vague to
    implement safely, or ``None`` if requirements look concrete enough.

    Checks:
    - Body is missing or shorter than *min_body_length* characters.
    - Body contains fewer than ``_MIN_REQUIREMENT_WORDS`` words.
    - Body contains nothing but vague verbs (improve / fix / enhance …).
    """
    title = task.get("title", "(untitled)")
    body = (task.get("body") or "").strip()
    filename = task.get("source", "")

    details: list[str] = []

    if len(body) < min_body_length:
        details.append(
            f"Body is only {len(body)} characters "
            f"(minimum {min_body_length} expected)."
        )

    word_count = len(body.split())
    if word_count < _MIN_REQUIREMENT_WORDS:
        details.append(
            f"Body contains only {word_count} words — not enough to be actionable."
        )

    if body and _VAGUE_ONLY.match(body):
        details.append(
            f"Body appears to contain only a vague directive: {body!r:.80}"
        )

    if not details:
        return None

    return EscalationTrigger(
        reason=AMBIGUOUS_TASK,
        message=f"Task '{title}' has ambiguous requirements.",
        task_filename=filename,
        details=details,
    )


# ---------------------------------------------------------------------------
# Repeated-failure detection
# ---------------------------------------------------------------------------

def check_repeated_failures(
    error_messages: list[str],
    threshold: int = 3,
    task_filename: str = "",
) -> Optional[EscalationTrigger]:
    """
    Return a trigger when the number of consecutive failure messages meets or
    exceeds *threshold*, otherwise ``None``.

    *error_messages* should be the list of error strings from the most recent
    consecutive failures (e.g. from RecoveryTracker).
    """
    count = len(error_messages)
    if count < threshold:
        return None

    details = [f"Failure {i + 1}: {msg[:119]}" for i, msg in enumerate(error_messages)]
    return EscalationTrigger(
        reason=REPEATED_FAILURES,
        message=(
            f"{count} consecutive failure{'s' if count != 1 else ''} "
            f"on{(' ' + task_filename) if task_filename else ' this task'}."
        ),
        task_filename=task_filename,
        details=details,
    )


# ---------------------------------------------------------------------------
# Risky code detection
# ---------------------------------------------------------------------------

_RISKY_PATTERNS: list[tuple[str, str]] = [
    # Schema / data mutations (distinct from reviewer's DROP TABLE block)
    (r"ALTER\s+TABLE",                    "schema alteration (ALTER TABLE)"),
    (r"ADD\s+COLUMN|DROP\s+COLUMN|add_column|drop_column",
                                          "column change (ADD/DROP COLUMN)"),
    (r"CREATE\s+TABLE",                   "new table definition (CREATE TABLE)"),
    (r"alembic|flask_migrate|migrate\.upgrade|migrate\.downgrade",
                                          "database migration tool"),
    # Authentication and secrets
    (r"\b(?:SECRET_KEY|JWT_SECRET|PRIVATE_KEY)\b",
                                          "secret key reference"),
    (r"bcrypt|scrypt|passlib|argon2",     "password hashing library"),
    (r"@login_required|require_login|@jwt_required",
                                          "authentication decorator"),
    # Payment processing
    (r"stripe|braintree|paypal|twilio",   "third-party payment/comms API"),
    (r"charge\(|subscription\.|invoice\.", "billing operation"),
    # Infrastructure / deployment
    (r"boto3|s3\.upload|s3_client",       "AWS S3 operation"),
    (r"docker|kubectl|helm\b",            "container/orchestration tooling"),
    (r"subprocess.*deploy|os\.system.*deploy",
                                          "deployment subprocess call"),
    # Sensitive config files
    (r"settings\.py|config\.py",         "application config file"),
    (r"Procfile|railway\.toml|\.env\b",  "deployment / environment config"),
]


def check_risky_code(
    patch_content: str,
    task_filename: str = "",
) -> Optional[EscalationTrigger]:
    """
    Scan *patch_content* for patterns that require a human sign-off even
    when technically valid.  Returns an :class:`EscalationTrigger` listing
    every matched pattern, or ``None`` if the patch looks routine.

    This is complementary to ``reviewer.review()`` which blocks outright
    dangerous operations; this check flags code that is *allowed* but
    *sensitive* enough to warrant a second set of eyes.
    """
    hits: list[str] = []
    for pattern, label in _RISKY_PATTERNS:
        if re.search(pattern, patch_content, re.IGNORECASE):
            hits.append(label)

    if not hits:
        return None

    return EscalationTrigger(
        reason=RISKY_CODE,
        message=(
            f"Patch{(' for ' + task_filename) if task_filename else ''} "
            f"touches {len(hits)} sensitive code path(s)."
        ),
        task_filename=task_filename,
        details=[f"- {h}" for h in hits],
    )


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

def should_escalate(triggers: list[Optional[EscalationTrigger]]) -> bool:
    """Return True if any trigger in the list is non-None."""
    return any(t is not None for t in triggers)


def write_escalation_report(
    triggers: list[EscalationTrigger],
    path: Path = DEFAULT_ESCALATE_PATH,
    append: bool = False,
) -> Path:
    """
    Write (or append to) *path* with a structured escalation report.

    The file blocks the autonomous loop — the engineer must delete it to
    resume.  Returns the path that was written.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        f"# Escalation Notice — {ts}",
        "",
        "Human review is required before the autonomous loop can continue.",
        "**Delete this file to resume.**",
        "",
        f"## Triggers ({len(triggers)})",
        "",
    ]

    for i, t in enumerate(triggers, 1):
        lines += [
            f"### {i}. {t.reason.replace('_', ' ').title()}",
            "",
            f"**Task:** `{t.task_filename or '(unknown)'}`",
            f"**Message:** {t.message}",
            "",
        ]
        if t.details:
            lines.append("**Details:**")
            lines.append("")
            for detail in t.details:
                lines.append(f"  {detail}")
            lines.append("")

    lines += [
        "## Resolution Steps",
        "",
        "1. Review the details above.",
        "2. For **ambiguous tasks**: clarify the task specification.",
        "3. For **repeated failures**: inspect `ai_agent/logs/` and fix the root cause.",
        "4. For **risky code**: review the proposed patch manually before applying.",
        "5. Delete this file to allow the loop to resume.",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path
