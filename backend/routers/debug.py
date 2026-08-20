"""
Debug endpoints for pivot engine visualization.
Temporary — not for production use.
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.price_cache import PriceCache
from services.pivot_engine import (
    compute_pivots_for_timeframe,
    find_pivot_highs_lows,
    _find_uptrend_abc,
    _find_downtrend_abc,
    _price_on_correct_side,
    _d_has_established,
    _compute_d_extended,
    update_c_dynamically,
    update_b_dynamically,
    _MAX_A_LOOKBACK,
    _STALE_C_DAYS,
    TIMEFRAMES,
    _trading_days_since,
)
import services.pivot_engine as pivot_engine
import pandas_market_calendars as mcal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/debug", tags=["debug"])

_NYSE = mcal.get_calendar("NYSE")
_ET = ZoneInfo("America/New_York")


def _sim_trading_days_since_fn(date_str, sim_date_str):
    try:
        schedule = _NYSE.schedule(start_date=date_str, end_date=sim_date_str)
        return max(0, len(schedule) - 1)
    except Exception:
        return 0


def _diagnose_no_structure(prices, dates, timeframe, bar_window, a_lookback_override):
    """
    Run the same internal steps as compute_pivots_for_timeframe but capture
    intermediate results for debugging why NO_STRUCTURE was returned.
    """
    diag = {}
    pivot_highs, pivot_lows = find_pivot_highs_lows(prices, bar_window)
    diag["pivot_highs_count"] = len(pivot_highs)
    diag["pivot_lows_count"] = len(pivot_lows)

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        diag["reason"] = "insufficient_pivots"
        return diag

    max_a_lookback = a_lookback_override if a_lookback_override is not None else _MAX_A_LOOKBACK.get(timeframe)
    if max_a_lookback is not None and len(prices) > max_a_lookback:
        cutoff_idx = max(0, len(prices) - max_a_lookback - bar_window)
        filtered_highs = [(i, p) for i, p in pivot_highs if i >= cutoff_idx]
        filtered_lows = [(i, p) for i, p in pivot_lows if i >= cutoff_idx]
    else:
        cutoff_idx = 0
        filtered_highs = pivot_highs
        filtered_lows = pivot_lows

    diag["cutoff_idx"] = cutoff_idx
    diag["cutoff_date"] = dates[cutoff_idx] if cutoff_idx < len(dates) else None
    diag["filtered_highs_count"] = len(filtered_highs)
    diag["filtered_lows_count"] = len(filtered_lows)
    diag["filtered_highs"] = [{"idx": i, "price": round(p, 4), "date": dates[i]} for i, p in filtered_highs[-6:]]
    diag["filtered_lows"] = [{"idx": i, "price": round(p, 4), "date": dates[i]} for i, p in filtered_lows[-6:]]

    raw_up = _find_uptrend_abc(filtered_highs, filtered_lows)
    raw_dn = _find_downtrend_abc(filtered_highs, filtered_lows)
    diag["raw_uptrend"] = _fmt_abc(raw_up, dates) if raw_up else None
    diag["raw_downtrend"] = _fmt_abc(raw_dn, dates) if raw_dn else None

    if not raw_up and not raw_dn:
        diag["reason"] = "no_abc_candidates"
        return diag

    walked_up = walked_dn = None
    if raw_up:
        walked_up = update_c_dynamically(raw_up, pivot_highs, pivot_lows)
        walked_up = update_b_dynamically(walked_up, pivot_highs, pivot_lows)
        diag["walked_uptrend"] = _fmt_abc(walked_up, dates)
    if raw_dn:
        walked_dn = update_c_dynamically(raw_dn, pivot_highs, pivot_lows)
        walked_dn = update_b_dynamically(walked_dn, pivot_highs, pivot_lows)
        diag["walked_downtrend"] = _fmt_abc(walked_dn, dates)

    current_price = prices[-1]
    diag["current_price"] = round(current_price, 4)

    if walked_up:
        up_ext = _compute_d_extended(walked_up, prices)
        up_break = walked_up["b"] if up_ext else walked_up["c"]
        diag["up_intact"] = _price_on_correct_side(walked_up, current_price, prices)
        diag["up_d_extended"] = up_ext
        diag["up_break_level"] = round(up_break, 4)
        diag["up_d_established"] = _d_has_established(walked_up, prices)
    if walked_dn:
        dn_ext = _compute_d_extended(walked_dn, prices)
        dn_break = walked_dn["b"] if dn_ext else walked_dn["c"]
        diag["dn_intact"] = _price_on_correct_side(walked_dn, current_price, prices)
        diag["dn_d_extended"] = dn_ext
        diag["dn_break_level"] = round(dn_break, 4)
        diag["dn_d_established"] = _d_has_established(walked_dn, prices)

    if walked_up and walked_dn:
        up_ok = diag.get("up_intact", False)
        dn_ok = diag.get("dn_intact", False)
        if not up_ok and not dn_ok:
            diag["reason"] = "both_broken"
        elif up_ok and dn_ok:
            diag["reason"] = "both_intact_tiebreak"
        else:
            diag["reason"] = "one_intact_one_broken"
    elif walked_up:
        diag["reason"] = "only_uptrend_found"
    elif walked_dn:
        diag["reason"] = "only_downtrend_found"

    # Check stale C — the engine may have found a valid structure but
    # rejected it because C is too old.
    max_c_age = _STALE_C_DAYS.get(timeframe)
    winner = None
    if walked_up and diag.get("up_intact"):
        winner = walked_up
    elif walked_dn and diag.get("dn_intact"):
        winner = walked_dn
    elif walked_up:
        winner = walked_up
    elif walked_dn:
        winner = walked_dn

    if winner and max_c_age is not None:
        c_date_str = dates[winner["c_idx"]]
        c_age = _sim_trading_days_since_fn(c_date_str, dates[-1])
        diag["stale_c_check"] = {
            "c_date": c_date_str,
            "c_age_days": c_age,
            "max_age": max_c_age,
            "is_stale": c_age > max_c_age,
        }
        if c_age > max_c_age:
            diag["reason"] = f"stale_c ({c_age}d > {max_c_age}d cutoff)"

    return diag


def _fmt_abc(abc, dates):
    if not abc:
        return None
    return {
        "direction": abc["direction"],
        "a": round(abc["a"], 4),
        "b": round(abc["b"], 4),
        "c": round(abc["c"], 4),
        "a_date": dates[abc["a_idx"]] if abc["a_idx"] < len(dates) else None,
        "b_date": dates[abc["b_idx"]] if abc["b_idx"] < len(dates) else None,
        "c_date": dates[abc["c_idx"]] if abc["c_idx"] < len(dates) else None,
        "a_idx": abc["a_idx"],
        "b_idx": abc["b_idx"],
        "c_idx": abc["c_idx"],
    }


@router.get("/pivots")
def debug_pivots(
    ticker: str = Query(...),
    timeframe: str = Query("trade"),
    bar_window: int = Query(None),
    a_lookback: int = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
):
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if not row or not row.history_json or not row.history_dates_json:
        return {"error": f"No history for {ticker}"}

    all_prices = json.loads(row.history_json)
    all_dates = json.loads(row.history_dates_json)

    if bar_window is None:
        bar_window = TIMEFRAMES.get(timeframe, 5)

    # Find date range indices
    start_idx = 0
    end_idx = len(all_dates) - 1

    if start_date:
        for i, d in enumerate(all_dates):
            if d >= start_date:
                start_idx = i
                break

    if end_date:
        for i in range(len(all_dates) - 1, -1, -1):
            if all_dates[i] <= end_date:
                end_idx = i
                break

    # We need enough warmup bars before start_date for pivot detection.
    # Use all available history before start_idx as warmup.
    # The chart will only show start_idx..end_idx but the engine sees 0..current_bar.
    warmup_start = 0

    # Monkey-patch _trading_days_since so stale-C uses simulated date
    original_fn = pivot_engine._trading_days_since
    _sim_date_holder = [None]

    def _sim_trading_days_since(date_str):
        try:
            sim = _sim_date_holder[0]
            if sim is None:
                return original_fn(date_str)
            schedule = _NYSE.schedule(start_date=date_str, end_date=str(sim))
            return max(0, len(schedule) - 1)
        except Exception:
            return 0

    pivot_engine._trading_days_since = _sim_trading_days_since

    try:
        trail = []
        prior = None  # prior bar's entry for break persistence

        for bar_idx in range(start_idx, end_idx + 1):
            price_slice = all_prices[: bar_idx + 1]
            date_slice = all_dates[: bar_idx + 1]
            _sim_date_holder[0] = all_dates[bar_idx]

            result = compute_pivots_for_timeframe(
                price_slice, date_slice, timeframe, bar_window,
                max_a_lookback_override=a_lookback,
            )

            entry = {
                "date": all_dates[bar_idx],
                "price": all_prices[bar_idx],
                "bar_index": bar_idx,
                "state": result.get("structural_state", "NO_STRUCTURE"),
                "direction": result.get("direction"),
                "d_extended": result.get("d_extended", False),
                "pivot_a": result.get("pivot_a"),
                "pivot_b": result.get("pivot_b"),
                "pivot_c": result.get("pivot_c"),
                "pivot_d": result.get("pivot_d"),
                "pivot_a_date": result.get("pivot_a_date"),
                "pivot_b_date": result.get("pivot_b_date"),
                "pivot_c_date": result.get("pivot_c_date"),
                "pivot_d_date": result.get("pivot_d_date"),
            }

            if result.get("structural_state") == "NO_STRUCTURE":
                entry["diag"] = _diagnose_no_structure(
                    price_slice, date_slice, timeframe, bar_window, a_lookback,
                )

            # Save engine's raw result before persistence layer may override
            entry["engine_state"] = entry["state"]
            entry["engine_direction"] = entry["direction"]
            entry["engine_pivots"] = {
                "a": result.get("pivot_a"),
                "b": result.get("pivot_b"),
                "c": result.get("pivot_c"),
                "d": result.get("pivot_d"),
                "a_date": result.get("pivot_a_date"),
                "b_date": result.get("pivot_b_date"),
                "c_date": result.get("pivot_c_date"),
                "d_date": result.get("pivot_d_date"),
                "d_extended": result.get("d_extended", False),
            }

            # --- Break persistence layer ---
            # When the engine loses the held structure (stale C, A aging,
            # both-broken, or finds a different structure), check the held
            # break level. Only transition when price actually crosses it.
            if prior is not None:
                prior_state = prior["state"]
                prior_break = prior.get("break_level")
                price = entry["price"]

                prior_was_valid = prior_state in ("UPTREND_VALID", "DOWNTREND_VALID")
                prior_was_break = prior_state in ("BREAK_OF_TRADE", "BREAK_OF_TREND")

                engine_same_valid = (
                    (prior_state == "UPTREND_VALID" and entry["state"] == "UPTREND_VALID") or
                    (prior_state == "DOWNTREND_VALID" and entry["state"] == "DOWNTREND_VALID")
                )

                if prior_was_valid and not engine_same_valid and prior_break is not None:
                    prior_dir = prior.get("direction")
                    price_broke = (
                        (prior_dir == "uptrend" and price < prior_break) or
                        (prior_dir == "downtrend" and price > prior_break)
                    )
                    if price_broke:
                        break_type = "BREAK_OF_TREND" if timeframe == "trend" else "BREAK_OF_TRADE"
                        entry.update({
                            "state": break_type,
                            "direction": prior_dir,
                            "d_extended": prior["d_extended"],
                            "pivot_a": prior["pivot_a"],
                            "pivot_b": prior["pivot_b"],
                            "pivot_c": prior["pivot_c"],
                            "pivot_d": prior["pivot_d"],
                            "pivot_a_date": prior["pivot_a_date"],
                            "pivot_b_date": prior["pivot_b_date"],
                            "pivot_c_date": prior["pivot_c_date"],
                            "pivot_d_date": prior["pivot_d_date"],
                        })
                    else:
                        entry.update({
                            "state": prior_state,
                            "direction": prior_dir,
                            "d_extended": prior["d_extended"],
                            "pivot_a": prior["pivot_a"],
                            "pivot_b": prior["pivot_b"],
                            "pivot_c": prior["pivot_c"],
                            "pivot_d": prior["pivot_d"],
                            "pivot_a_date": prior["pivot_a_date"],
                            "pivot_b_date": prior["pivot_b_date"],
                            "pivot_c_date": prior["pivot_c_date"],
                            "pivot_d_date": prior["pivot_d_date"],
                        })

                elif prior_was_break and prior_break is not None:
                    prior_dir = prior.get("direction")
                    still_broken = (
                        (prior_dir == "uptrend" and price < prior_break) or
                        (prior_dir == "downtrend" and price > prior_break)
                    )
                    if still_broken:
                        entry.update({
                            "state": "BREAK_CONFIRMED",
                            "direction": prior_dir,
                            "d_extended": prior["d_extended"],
                            "pivot_a": prior["pivot_a"],
                            "pivot_b": prior["pivot_b"],
                            "pivot_c": prior["pivot_c"],
                            "pivot_d": prior["pivot_d"],
                            "pivot_a_date": prior["pivot_a_date"],
                            "pivot_b_date": prior["pivot_b_date"],
                            "pivot_c_date": prior["pivot_c_date"],
                            "pivot_d_date": prior["pivot_d_date"],
                        })
                    # If price recovered, let the engine result stand

            # Compute break level
            if entry["state"] != "NO_STRUCTURE":
                if entry["d_extended"] and entry["pivot_b"] is not None:
                    entry["break_level"] = entry["pivot_b"]
                elif entry["pivot_c"] is not None:
                    entry["break_level"] = entry["pivot_c"]
                else:
                    entry["break_level"] = None
            else:
                entry["break_level"] = None

            prior = entry
            trail.append(entry)
    finally:
        pivot_engine._trading_days_since = original_fn

    # Build price series for the visible range
    prices = []
    for i in range(start_idx, end_idx + 1):
        prices.append({"date": all_dates[i], "price": all_prices[i]})

    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "bar_window": bar_window,
        "start_date": all_dates[start_idx],
        "end_date": all_dates[end_idx],
        "total_history_bars": len(all_prices),
        "prices": prices,
        "trail": trail,
    }
