#!/usr/bin/env python3
"""PreToolUse gate guard for the government-recompete-monitor repo.

Blocks a fixed set of high-risk git/gh operations UNLESS an explicit approval
file exists at /home/michael/.gate_approval. Designed to fail CLOSED: any
uncertainty (unparseable input, malformed command, unreadable gate file) results
in a DENY for a matched dangerous command.

Denied without approval:
  - git merge ...
  - git push ... origin ... main       (pushing to main)
  - git push ... --force / -f / --force-with-lease   (any force-push)
  - gh pr merge ...
  - git add ... integration/recompete_report.csv

Non-matching commands and non-Bash tools pass through untouched (exit 0, no
output) so the normal Claude Code permission flow still applies.

Protocol: reads the PreToolUse JSON payload on stdin, emits a
hookSpecificOutput.permissionDecision of "deny" to block. Silence + exit 0 is a
pass-through (NOT a force-allow), so other permission rules remain in effect.
"""
import sys
import os
import re
import json

GATE = "/home/michael/.gate_approval"

# (compiled regex, human label). Patterns are matched against a single command
# segment (see _segments) with whitespace normalized. Over-blocking is the safe
# direction for a fail-closed gate, so patterns are deliberately broad.
PATTERNS = [
    (re.compile(r"\bgit\s+merge\b"), "git merge"),
    (re.compile(r"\bgit\s+push\b.*\borigin\b.*\bmain\b"), "git push origin main"),
    (re.compile(r"\bgit\s+push\b.*(--force-with-lease|--force\b|(^|\s)-f\b)"), "force-push"),
    (re.compile(r"\bgh\s+pr\s+merge\b"), "gh pr merge"),
    (re.compile(r"\bgit\s+add\b.*integration/recompete_report\.csv\b"),
     "git add integration/recompete_report.csv"),
]


def _emit_deny(reason):
    """Emit a PreToolUse deny decision and exit 0 (the decision is in the JSON)."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _passthrough():
    """No decision: let the normal permission flow handle this command."""
    sys.exit(0)


def _segments(command):
    """Split a shell command into rough segments on separators/operators so a
    match in one clause isn't diluted by unrelated text elsewhere."""
    parts = re.split(r"(?:&&|\|\||[;&|\n])", command)
    return [" ".join(p.split()) for p in parts if p.strip()]


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        # Cannot see the command at all -> cannot certify it safe. Fail closed.
        _emit_deny("gate-guard: unparseable PreToolUse payload; failing closed.")

    if data.get("tool_name") != "Bash":
        _passthrough()

    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        _emit_deny("gate-guard: missing/malformed Bash command; failing closed.")

    matched = None
    for seg in _segments(command):
        for pattern, label in PATTERNS:
            if pattern.search(seg):
                matched = label
                break
        if matched:
            break

    if matched is None:
        _passthrough()

    # A dangerous op was matched. The ONLY way through is a confirmed gate file.
    try:
        gate_open = os.path.isfile(GATE)
    except Exception:
        gate_open = False  # unreadable -> fail closed

    if gate_open:
        # Approval present. Pass through (do not force-allow) so other rules
        # still apply; the operator has explicitly opened the gate.
        _passthrough()

    _emit_deny(
        f"gate-guard: '{matched}' is blocked without Discord approval. "
        f"Create {GATE} to open the gate, then retry. Failing closed."
    )


if __name__ == "__main__":
    main()
