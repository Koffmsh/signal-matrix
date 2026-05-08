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

# Base URL for links inside email bodies. Override in local .env so reset/login
# links point at localhost:3000 during dev. Defaults to production.
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://signal.suttonmc.com").rstrip("/")


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


def send_email_to(recipient: str, subject: str, body: str) -> bool:
    """
    Send email to an arbitrary recipient. Used for password reset links and
    duplicate-registration notices. Matches send_email() SMTP setup exactly.
    """
    if not all([_FROM, _PASSWORD]):
        logger.warning("Email: credentials not configured — skipping send")
        return False

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = _FROM
        msg["To"]      = recipient

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(_FROM, _PASSWORD)
            smtp.sendmail(_FROM, recipient, msg.as_string())

        logger.info(f"Email sent to {recipient}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def send_new_user_notification(
    email: str,
    display_name: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Alerts Shannon when a genuinely new user registers."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et_now = datetime.now(ZoneInfo("America/New_York")).strftime("%m/%d/%y %H:%M ET")

    subject = f"Signal Matrix — New Registration: {display_name or email}"
    body = f"""
New user registration pending your approval.

Email:        {email}
Display name: {display_name or '(not provided)'}
Registered:   {et_now}
IP address:   {ip_address or 'unknown'}
User agent:   {user_agent or 'unknown'}

Approve or disable at:
{APP_BASE_URL}/admin/users
""".strip()
    send_email(subject, body)


def send_duplicate_registration_notice(email: str) -> None:
    """Sent to the registered address when someone tries to register with an already-taken email.
    Tells the owner without revealing to the requester that the email exists."""
    subject = "Signal Matrix — Registration Attempt"
    body = f"""
Someone tried to register a Signal Matrix account using your email address.

If that was you, you already have an account. You can log in or reset your password at:
{APP_BASE_URL}/login

If this wasn't you, no action is needed — no changes were made to your account.
""".strip()
    send_email_to(email, subject, body)


def send_password_reset_email(email: str, reset_token: str) -> None:
    """Send password reset link to the user."""
    reset_url = f"{APP_BASE_URL}/reset-password?token={reset_token}"
    subject = "Signal Matrix — Password Reset"
    body = f"""
You requested a password reset for your Signal Matrix account.

Reset your password here (link expires in 15 minutes):
{reset_url}

If you did not request this, ignore this email — no changes will be made.
""".strip()
    send_email_to(email, subject, body)
