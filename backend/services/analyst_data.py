"""
Analyst Momentum Data — yfinance upgrades_downgrades + price targets.

On-demand fetch (not scheduled) — called from the security detail endpoint.
Only works for individual stocks; ETFs/indices/futures return None.
"""
import logging
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

BUY_GRADES = frozenset({
    "buy", "strong buy", "outperform", "overweight", "positive",
    "sector outperform", "market outperform", "top pick", "conviction buy",
    "accumulate", "add",
})
SELL_GRADES = frozenset({
    "sell", "strong sell", "underperform", "underweight", "negative",
    "sector underperform", "market underperform", "reduce",
})

_GRADE_RANK = {"sell": 0, "hold": 1, "buy": 2}


def _classify_grade(grade: str) -> str:
    if not grade:
        return "hold"
    g = grade.strip().lower()
    if g in BUY_GRADES:
        return "buy"
    if g in SELL_GRADES:
        return "sell"
    return "hold"


def fetch_analyst_data(ticker: str) -> dict | None:
    """Fetch analyst upgrades/downgrades + price targets for a single ticker.

    Returns None if no data available (ETFs, indices, futures).
    Returns a dict with momentum metrics if data exists.
    """
    try:
        t = yf.Ticker(ticker)
        ud = t.upgrades_downgrades
    except Exception as e:
        logger.debug("analyst_data: %s fetch failed: %s", ticker, e)
        return None

    result = {}

    # Price targets
    try:
        pt = t.analyst_price_targets
        if pt and isinstance(pt, dict) and pt.get("mean"):
            current = pt.get("current")
            mean = pt.get("mean")
            result["price_targets"] = {
                "current": current,
                "mean": mean,
                "median": pt.get("median"),
                "low": pt.get("low"),
                "high": pt.get("high"),
                "upside_pct": round((mean / current - 1) * 100, 1) if current and mean else None,
            }
    except Exception:
        pass

    if ud is None or ud.empty:
        if not result.get("price_targets"):
            return None
        result["has_ratings"] = False
        return result

    result["has_ratings"] = True
    now = datetime.now()

    ud = ud.copy()
    ud["from_class"] = ud["FromGrade"].apply(_classify_grade)
    ud["to_class"] = ud["ToGrade"].apply(_classify_grade)
    ud["delta"] = ud["to_class"].map(_GRADE_RANK) - ud["from_class"].map(_GRADE_RANK)

    # Rating momentum over windows
    for label, days in [("30d", 30), ("90d", 90), ("180d", 180)]:
        cutoff = now - timedelta(days=days)
        window = ud[ud.index >= cutoff]
        upgrades = int((window["delta"] > 0).sum()) if not window.empty else 0
        downgrades = int((window["delta"] < 0).sum()) if not window.empty else 0
        result[f"upgrades_{label}"] = upgrades
        result[f"downgrades_{label}"] = downgrades
        result[f"net_{label}"] = upgrades - downgrades
        result[f"total_{label}"] = len(window)

    # Price target momentum (90D)
    cutoff_90 = now - timedelta(days=90)
    recent = ud[ud.index >= cutoff_90]
    if not recent.empty and "priceTargetAction" in recent.columns:
        pt_actions = recent["priceTargetAction"].str.lower().value_counts()
        raises = int(pt_actions.get("raises", 0))
        lowers = int(pt_actions.get("lowers", 0))
        result["pt_raises_90d"] = raises
        result["pt_lowers_90d"] = lowers
        result["pt_net_90d"] = raises - lowers

    # Current consensus (last rating per firm)
    latest_per_firm = ud.groupby("Firm").first()
    buy_count = int((latest_per_firm["to_class"] == "buy").sum())
    hold_count = int((latest_per_firm["to_class"] == "hold").sum())
    sell_count = int((latest_per_firm["to_class"] == "sell").sum())
    total = buy_count + hold_count + sell_count
    buy_pct = round(buy_count / total * 100, 1) if total else 0
    result["consensus"] = {
        "buy": buy_count, "hold": hold_count, "sell": sell_count,
        "total": total, "buy_pct": buy_pct,
    }
    result["peak_consensus"] = buy_pct >= 90

    # Days since last upgrade
    upgrades_only = ud[ud["delta"] > 0]
    if not upgrades_only.empty:
        last_upgrade = upgrades_only.index[0]
        result["days_since_upgrade"] = (now - last_upgrade.to_pydatetime().replace(tzinfo=None)).days
    else:
        result["days_since_upgrade"] = None

    # Recent rating actions (last 10 for UI display)
    actions = []
    for idx, row in ud.head(10).iterrows():
        actions.append({
            "date": idx.strftime("%Y-%m-%d"),
            "firm": row["Firm"],
            "action": row["Action"],
            "from_grade": row["FromGrade"] or None,
            "to_grade": row["ToGrade"],
            "pt_action": row.get("priceTargetAction") or None,
            "pt_current": row.get("currentPriceTarget") if row.get("currentPriceTarget") else None,
            "pt_prior": row.get("priorPriceTarget") if row.get("priorPriceTarget") else None,
        })
    result["recent_actions"] = actions

    # Composite momentum signal
    net_90 = result.get("net_90d", 0)
    pt_net = result.get("pt_net_90d", 0)
    peak = result.get("peak_consensus", False)

    if peak and net_90 <= 0:
        result["momentum_signal"] = "Peak Consensus"
    elif net_90 >= 3 or (net_90 >= 2 and pt_net >= 3):
        result["momentum_signal"] = "Strong Upgrade"
    elif net_90 >= 1 or (net_90 >= 0 and pt_net >= 3):
        result["momentum_signal"] = "Upgrade"
    elif net_90 <= -2 or (net_90 < 0 and pt_net <= -3):
        result["momentum_signal"] = "Downgrade"
    elif net_90 <= -1 or (net_90 <= 0 and pt_net <= -2):
        result["momentum_signal"] = "Moderate Downgrade"
    else:
        result["momentum_signal"] = "Neutral"

    return result
