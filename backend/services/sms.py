"""
sms.py — Twilio SMS wrapper.

Reads credentials from environment variables:
  TWILIO_ACCOUNT_SID  — Twilio account SID
  TWILIO_AUTH_TOKEN   — Twilio auth token
  TWILIO_FROM         — Twilio phone number  (e.g. +12025551234)
  TWILIO_TO           — your mobile number   (e.g. +14155551234)

If any env var is missing, send_sms() logs a warning and no-ops —
alerts will not crash the intraday monitor.
"""

import os
import logging

logger = logging.getLogger(__name__)

_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
_FROM        = os.getenv("TWILIO_FROM")
_TO          = os.getenv("TWILIO_TO")


def send_sms(message: str) -> bool:
    """
    Send an SMS via Twilio. Returns True on success, False on failure.
    No-ops silently when credentials are not configured.
    """
    if not all([_ACCOUNT_SID, _AUTH_TOKEN, _FROM, _TO]):
        logger.warning("SMS: Twilio credentials not configured — skipping send")
        return False

    try:
        from twilio.rest import Client
        client = Client(_ACCOUNT_SID, _AUTH_TOKEN)
        client.messages.create(body=message, from_=_FROM, to=_TO)
        logger.info(f"SMS sent: {message[:60]}...")
        return True
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return False
