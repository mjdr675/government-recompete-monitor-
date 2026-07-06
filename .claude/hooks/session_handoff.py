#!/usr/bin/env python3
"""Stop hook: post the session's final report to the Recompete handoffs channel.

On Claude Code session stop, posts the session's final report to Discord via the
``AE_DISCORD_WEBHOOK_URL`` webhook -- the same channel where task-done / handoff
summaries already land. Report source, in priority order:
  1. FINAL_REPORT.md at the session cwd (or repo root) if present.
  2. Otherwise the last assistant text message in the session transcript.

FAIL-OPEN BY CONSTRUCTION: every failure (no webhook, Discord down/timeout,
malformed transcript, missing file, bad stdin) is caught, logged locally to
.claude/hooks/handoff_hook.log, and the hook exits 0. It can NEVER block a
session from stopping and never raises. Mirrors the never-raises shape of the
operator-brain gate notifier (operator-bot/operator_brain/gate_notifications.py).

The operator webhook (OPERATOR_DISCORD_WEBHOOK) is deliberately NOT used here --
that channel is reserved for gate/approval events.
"""
from __future__ import annotations

import sys
import os
import json
import datetime
import urllib.request
import urllib.error

# .../repo/.claude/hooks/session_handoff.py -> repo root is three dirs up.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_PATH = os.path.join(REPO_ROOT, ".claude", "hooks", "handoff_hook.log")
# Interactive Claude sessions don't inherit the systemd EnvironmentFile, so fall
# back to reading the webhook from the same secrets file the bot service uses.
SECRETS_ENV = os.path.expanduser("~/.config/secrets/env")
WEBHOOK_ENV = "AE_DISCORD_WEBHOOK_URL"
# Discord 403s urllib's default UA, so an explicit UA is mandatory (see the 403
# fix in operator-bot commit 591cf38).
USER_AGENT = "recompete-stop-hook/1.0 (+https://github.com/mjdr675)"
DISCORD_LIMIT = 2000
POST_TIMEOUT_SECONDS = 10


def log(msg: str) -> None:
    """Append a line to the local hook log. Never raises."""
    try:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        with open(LOG_PATH, "a") as f:
            f.write(f"{ts} {msg}\n")
    except Exception:
        pass


def read_webhook() -> str:
    """Webhook URL from the environment, else from the secrets env file."""
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if url:
        return url
    try:
        with open(SECRETS_ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith(WEBHOOK_ENV + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception as e:
        log(f"secrets read failed: {e!r}")
    return ""


def last_assistant_text(transcript_path: str) -> str:
    """Concatenated text blocks of the LAST assistant message in the transcript."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""
    last = ""
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") != "assistant":
                    continue
                content = (obj.get("message") or {}).get("content")
                parts = []
                if isinstance(content, list):
                    for blk in content:
                        if isinstance(blk, dict) and blk.get("type") == "text":
                            parts.append(blk.get("text", ""))
                elif isinstance(content, str):
                    parts.append(content)
                joined = "\n".join(p for p in parts if p).strip()
                if joined:
                    last = joined  # keep overwriting -> ends on the final one
    except Exception as e:
        log(f"transcript parse failed: {e!r}")
    return last


def final_report(payload: dict) -> tuple[str, str]:
    """(report_text, source_label). FINAL_REPORT.md wins; else last assistant msg."""
    cwd = payload.get("cwd") or REPO_ROOT
    seen = []
    for base in (cwd, REPO_ROOT):
        if base in seen:
            continue
        seen.append(base)
        p = os.path.join(base, "FINAL_REPORT.md")
        try:
            if os.path.isfile(p):
                with open(p) as f:
                    txt = f.read().strip()
                if txt:
                    return txt, f"FINAL_REPORT.md ({p})"
        except Exception as e:
            log(f"FINAL_REPORT read failed: {e!r}")
    txt = last_assistant_text(payload.get("transcript_path", ""))
    if txt:
        return txt, "last assistant message"
    return "", "none"


def truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    marker = "\n…[truncated]"
    return s[: max(0, limit - len(marker))] + marker


def post(webhook: str, content: str) -> int:
    body = json.dumps({
        "content": content,
        "username": "Recompete Session Handoff",
    }).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=POST_TIMEOUT_SECONDS) as resp:
        return resp.status


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except Exception as e:
        log(f"bad stdin payload: {e!r}")
        payload = {}

    session = payload.get("session_id", "?")

    try:
        report, source = final_report(payload)
    except Exception as e:
        log(f"final_report error: {e!r}")
        report, source = "", "error"

    if not report:
        log(f"session={session} no report content ({source}); nothing posted")
        sys.exit(0)

    webhook = read_webhook()
    if not webhook:
        log(f"session={session} no {WEBHOOK_ENV}; NOT posted (fail-open)")
        sys.exit(0)

    header = f"🤝 **Session handoff** · `{session}` · source: {source}\n"
    content = truncate(header + report, DISCORD_LIMIT)
    try:
        status = post(webhook, content)
        log(f"session={session} posted ok status={status} source={source} chars={len(content)}")
    except urllib.error.HTTPError as e:
        log(f"session={session} HTTPError {e.code} {e.reason} (fail-open)")
    except Exception as e:
        log(f"session={session} post failed: {e!r} (fail-open)")

    # Always exit 0: a Stop hook must never block a session from stopping.
    sys.exit(0)


if __name__ == "__main__":
    main()
