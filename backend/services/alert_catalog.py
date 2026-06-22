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
            "viewpoint ∈ {Bullish, Bearish} AND prox ≥ 0.85. "
            "Once per day."
        ),
    },
    {
        "key": "RETRACEMENT_50",
        "label": "50% Retracement",
        "description": (
            "structural_state ∈ {UPTREND_VALID, DOWNTREND_VALID} AND viewpoint aligned AND "
            "conviction ≥ 85 AND retracement ≥ 50% from D toward C. "
            "Once per day."
        ),
    },
]

ALERT_KEYS = {a["key"] for a in ALERT_CATALOG}
