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
            "Viewpoint Bullish or Bearish AND proximity ≥ 85% to the entry edge "
            "(LRR if Bullish, HRR if Bearish). Once per ticker per day."
        ),
    },
    {
        "key": "RETRACEMENT_50",
        "label": "50% Retracement",
        "description": (
            "State UPTREND_VALID/DOWNTREND_VALID AND viewpoint aligned AND "
            "conviction ≥ 85 AND price retraced ≥ 50% from the swing extreme (D) "
            "toward pivot C. Once per setup per day (resets on a new C)."
        ),
    },
]

ALERT_KEYS = {a["key"] for a in ALERT_CATALOG}
