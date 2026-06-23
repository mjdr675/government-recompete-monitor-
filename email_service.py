import logging
import os

import requests

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html_body: str, text_body: str = "") -> dict | None:
    api_key = os.environ.get("EMAIL_API_KEY", "")
    from_addr = os.environ.get("SMTP_FROM", "noreply@govrecompete.com")
    if not api_key:
        logger.warning("EMAIL_API_KEY not set — email not sent to %s", to)
        return None
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": from_addr,
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body or subject,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
