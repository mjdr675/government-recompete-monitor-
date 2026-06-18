"""
Email alert module.

Reads config from environment:
  ALERT_TO    — recipient address (required to send)
  SMTP_HOST   — default "localhost"
  SMTP_PORT   — default 587
  SMTP_USER   — optional, enables SMTP login
  SMTP_PASS   — optional, used with SMTP_USER
  SMTP_FROM   — sender address, default "alerts@recompete-monitor"
"""

import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from db import get_watchlist, get_changes


def _cfg():
    return {
        "to": os.environ.get("ALERT_TO", ""),
        "host": os.environ.get("SMTP_HOST", "localhost"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),
        "from_addr": os.environ.get("SMTP_FROM", "alerts@recompete-monitor"),
    }


def alert_config():
    """Return current config dict (with password masked)."""
    cfg = _cfg()
    return {k: ("***" if k == "password" and v else v) for k, v in cfg.items()}


def build_alert_body(run_date: str) -> str:
    """Build the plain-text email body for a given run date."""
    lines = [
        f"Government Recompete Monitor — Daily Alert",
        f"Date: {run_date}",
        "",
    ]

    watched = list(get_watchlist())
    if watched:
        lines.append(f"=== WATCHED CONTRACTS ({len(watched)}) ===")
        for r in watched:
            lines.append(
                f"  [{r['priority']}] {r['vendor']} / {r['agency']}"
                f" | ${r['value']:,.0f} | {r['days_remaining']} days | score {r['recompete_score']}"
            )
        lines.append("")

    upgrades = get_changes(run_date, "UPGRADE")
    if upgrades:
        lines.append(f"=== PRIORITY UPGRADES ({len(upgrades)}) ===")
        for row in upgrades:
            lines.append(
                f"  {row[5]} / {row[6]}"
                f" | {row[2]} → {row[3]}"
            )
        lines.append("")

    new_contracts = get_changes(run_date, "NEW") + get_changes(run_date, "NEW_TIER_A")
    if new_contracts:
        lines.append(f"=== NEW OPPORTUNITIES ({len(new_contracts)}) ===")
        for row in new_contracts:
            lines.append(
                f"  [{row[3] or row[2]}] {row[5]} / {row[6]}"
                f" | ${row[7]:,.0f}"
            )
        lines.append("")

    if not watched and not upgrades and not new_contracts:
        lines.append("No watched contracts, upgrades, or new opportunities today.")

    return "\n".join(lines)


def send_alert(run_date: str | None = None) -> dict:
    """
    Send the daily alert email.

    Returns {"sent": True} on success or {"sent": False, "reason": str} on skip/failure.
    """
    if run_date is None:
        run_date = date.today().isoformat()

    cfg = _cfg()
    if not cfg["to"]:
        return {"sent": False, "reason": "ALERT_TO not configured"}

    body = build_alert_body(run_date)
    subject = f"Recompete Monitor Alert — {run_date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = cfg["to"]
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as smtp:
            smtp.ehlo()
            if cfg["user"] and cfg["password"]:
                smtp.starttls()
                smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(cfg["from_addr"], [cfg["to"]], msg.as_string())
    except Exception as exc:
        return {"sent": False, "reason": str(exc)}

    return {"sent": True}
