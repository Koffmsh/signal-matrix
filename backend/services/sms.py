"""
sms.py — Twilio messaging wrapper (SMS or WhatsApp).

Reads credentials from environment variables:
  TWILIO_ACCOUNT_SID  — Twilio account SID
  TWILIO_AUTH_TOKEN   — Twilio auth token
  TWILIO_FROM         — Twilio phone number  (e.g. +12025551234)
  TWILIO_TO           — your mobile number   (e.g. +14155551234)
  TWILIO_CHANNEL      — 'whatsapp' | 'sms' (default: 'sms')

WhatsApp sandbox: set TWILIO_FROM to +14155238886 and TWILIO_CHANNEL to 'whatsapp'.
Recipient must first send the sandbox join message to that number.

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
_CHANNEL     = os.getenv("TWILIO_CHANNEL", "sms").lower()  # 'sms' | 'whatsapp'


def send_sms(message: str) -> bool:
    """
    Send a message via Twilio (SMS or WhatsApp). Returns True on success, False on failure.
    No-ops silently when credentials are not configured.
    """
    if not all([_ACCOUNT_SID, _AUTH_TOKEN, _FROM, _TO]):
        logger.warning("SMS: Twilio credentials not configured — skipping send")
        return False

    try:
        from twilio.rest import Client
        client = Client(_ACCOUNT_SID, _AUTH_TOKEN)

        if _CHANNEL == "whatsapp":
            from_addr = f"whatsapp:{_FROM}"
            to_addr   = f"whatsapp:{_TO}"
        else:
            from_addr = _FROM
            to_addr   = _TO

        client.messages.create(body=message, from_=from_addr, to=to_addr)
        logger.info(f"Alert sent via {_CHANNEL}: {message[:60]}...")
        return True
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return False
