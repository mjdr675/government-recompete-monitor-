import logging
import os

import jinja2

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "emails")
_jinja = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATE_DIR),
    autoescape=jinja2.select_autoescape(["html"]),
)


def render_email_template(template_name: str, context: dict | None = None) -> str:
    """Render an email template from templates/emails/ using a standalone Jinja2 env."""
    tmpl = _jinja.get_template(template_name)
    return tmpl.render(**(context or {}))


def build_pipeline_digest(user_id: int) -> dict | None:
    """Build a pipeline digest email payload for user_id.

    Returns dict with keys (subject, html, text), or None if the user has
    disabled email_notifications_enabled or pipeline_digest_enabled.
    """
    from db import get_notification_preferences, list_opportunities, PIPELINE_TERMINAL_STAGES

    prefs = get_notification_preferences(user_id)
    if not prefs["email_notifications_enabled"] or not prefs["pipeline_digest_enabled"]:
        return None

    all_opps = list_opportunities(user_id)
    active = [o for o in all_opps if o["stage"] not in PIPELINE_TERMINAL_STAGES]
    due_soon = sorted(
        [o for o in active if o.get("next_action_due")],
        key=lambda o: o["next_action_due"],
    )[:5]
    top = sorted(active, key=lambda o: -(o.get("recompete_score") or 0))[:5]

    html = render_email_template("pipeline_digest.html", {
        "active_count": len(active),
        "total_count": len(all_opps),
        "due_soon": due_soon,
        "top_opportunities": top,
    })
    noun = "opportunity" if len(active) == 1 else "opportunities"
    subject = f"Your Pipeline Digest — {len(active)} active {noun}"
    text = (
        f"You have {len(active)} active pipeline {noun}. "
        "Visit https://govrecompete.com/pipeline to view them."
    )
    return {"subject": subject, "html": html, "text": text}


def send_notification(to: str, subject: str, html: str, text: str = "") -> dict:
    """Send a notification email via the configured email adapter.

    Returns a result dict: {sent: bool, mode: str, error: str|None}.
    Safe when the email service is not configured — logs a warning and
    returns sent=False without raising.
    """
    from email_service import send_email

    try:
        result = send_email(to=to, subject=subject, html_body=html, text_body=text or subject)
    except Exception as exc:
        logger.warning("send_notification failed for %s: %s", to, exc)
        return {"sent": False, "mode": "error", "error": str(exc)}
    if result is None:
        return {"sent": False, "mode": "disabled", "error": "email service not configured"}
    return {"sent": True, "mode": "resend", "error": None}
