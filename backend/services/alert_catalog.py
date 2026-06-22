"""
alert_catalog.py — the canonical list of alert types the platform can deliver.

Single source of truth shared by:
  - routers/alerts.py   (serves labels/descriptions to the settings UI, validates keys)
  - services/intraday_monitor.py  (fires alerts by these keys)

Keys MUST match the alert_type strings written to intraday_alert_log.
Phase 1: two intraday alerts. Add new alerts here as they are built.
"""

ALERT_CATALOG = [
    {
        "key": "PROXIMITY",
        "label": "Proximity to Entry",
        "description": (
            "Fires when price reaches within 85% of the entry zone "
            "(between the LRR and HRR risk-range levels)."
        ),
    },
    {
        "key": "RETRACEMENT_50",
        "label": "50% Retracement",
        "description": (
            "Fires when price pulls back 50% from the recent swing extreme (D) "
            "back toward the invalidation pivot (C) — a pullback entry."
        ),
    },
]

ALERT_KEYS = {a["key"] for a in ALERT_CATALOG}
