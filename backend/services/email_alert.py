"""
email_alert.py — Gmail SMTP email notification service.

Reads credentials from environment variables:
  EMAIL_FROM         — Gmail address to send from
  EMAIL_TO           — destination address
  EMAIL_APP_PASSWORD — Gmail app password (16-char, spaces optional)

If any env var is missing, send_email() logs a warning and no-ops —
alerts will not crash the intraday monitor.
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_FROM     = os.getenv("EMAIL_FROM")
_TO       = os.getenv("EMAIL_TO")
_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "")  # strip spaces if any


def send_email(subject: str, body: str) -> bool:
    """
    Send an email via Gmail SMTP. Returns True on success, False on failure.
    No-ops silently when credentials are not configured.
    """
    if not all([_FROM, _TO, _PASSWORD]):
        logger.warning("Email: credentials not configured — skipping send")
        return False

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = _FROM
        msg["To"]      = _TO

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(_FROM, _PASSWORD)
            smtp.sendmail(_FROM, _TO, msg.as_string())

        logger.info(f"Email sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False
