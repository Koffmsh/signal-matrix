"""
sms.py — Telnyx messaging wrapper (SMS).

Reads credentials from environment variables:
  TELNYX_API_KEY  — Telnyx API v2 key
  TELNYX_FROM     — your Telnyx phone number (e.g. +14156196033)
  TELNYX_TO       — comma-separated recipient numbers (e.g. +14157107008,+14155551234)

If any env var is missing, send_sms() logs a warning and no-ops —
alerts will not crash the intraday monitor.
"""

import os
import logging
import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

_SMS_DISABLED = True  # disabled until 10DLC registration is complete

_API_KEY = os.getenv("TELNYX_API_KEY")
_FROM    = os.getenv("TELNYX_FROM")
_TO_RAW  = os.getenv("TELNYX_TO", "")
_TO_LIST = [n.strip() for n in _TO_RAW.split(",") if n.strip()]


def send_sms(message: str) -> bool:
    """
    Send an SMS to all recipients via Telnyx API v2. Returns True if all succeed.
    No-ops silently when disabled or credentials are not configured.
    """
    if _SMS_DISABLED:
        logger.info(f"SMS disabled — suppressed: {message[:80]}")
        return False

    if not all([_API_KEY, _FROM, _TO_LIST]):
        logger.warning("SMS: Telnyx credentials not configured — skipping send")
        return False

    success = True
    for to_number in _TO_LIST:
        try:
            payload = json.dumps({
                "from": _FROM,
                "to":   to_number,
                "text": message,
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.telnyx.com/v2/messages",
                data    = payload,
                headers = {
                    "Authorization": f"Bearer {_API_KEY}",
                    "Content-Type":  "application/json",
                },
                method  = "POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    logger.info(f"SMS sent to {to_number}: {message[:60]}...")
                else:
                    logger.error(f"SMS to {to_number} returned status {resp.status}")
                    success = False

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(f"SMS to {to_number} failed ({e.code}): {body}")
            success = False
        except Exception as e:
            logger.error(f"SMS to {to_number} failed: {e}")
            success = False

    return success
