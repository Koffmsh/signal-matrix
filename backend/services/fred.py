"""
FRED API client — fetches economic data series from the St. Louis Fed.

Usage:
    from services.fred import fetch_fred_series
    dates, values = fetch_fred_series("BAMLH0A0HYM2")

Rate limit: 120 requests/min (free tier). Daily data, ~1-day lag.
"""

import os
import logging
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("FRED_API_KEY", "")
_BASE = "https://api.stlouisfed.org/fred/series/observations"


def fetch_fred_series(
    series_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[str], list[float]]:
    """
    Fetch a FRED series and return (dates, values).

    Drops rows where value is "." (FRED's missing-value sentinel).
    Default window: 5 years back from today.
    """
    if not _API_KEY:
        logger.warning("FRED_API_KEY not set — returning empty series")
        return [], []

    if not start_date:
        start_date = (datetime.now() - timedelta(days=5 * 365)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    params = {
        "series_id": series_id,
        "api_key": _API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
        "sort_order": "asc",
    }

    try:
        resp = requests.get(_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("FRED fetch failed for %s: %s", series_id, e)
        return [], []

    observations = data.get("observations", [])

    dates = []
    values = []
    for obs in observations:
        v = obs.get("value")
        if v is None or v == ".":
            continue
        try:
            values.append(float(v))
            dates.append(obs["date"])
        except (ValueError, KeyError):
            continue

    logger.info("FRED %s: fetched %d observations (%s → %s)",
                series_id, len(dates),
                dates[0] if dates else "—",
                dates[-1] if dates else "—")
    return dates, values
