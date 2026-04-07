"""
schwab_options.py — Schwab options chain IV fetch.

Entry point: schwab_fetch_iv(db)
  - Fetches ATM implied volatility for IV-eligible tickers via Schwab options chains
  - Writes daily IV to iv_history table
  - Computes IV Rank (0-100) matching TOS methodology: (current-min)/(max-min)*100
  - Updates price_cache.rel_iv + price_cache.iv_source
  - Falls back to existing Yahoo proxy (iv_source = 'proxy') per ticker on any error
  - Idempotent within a trading day

IV source: ATM option contracts in callExpDateMap/putExpDateMap — NOT the top-level
  'volatility' field, which is historical/realized vol, not implied vol.

IV-eligible: all active Tier 1 tickers EXCEPT VIX, $DJI, SPX, NDX
  (index options have non-standard chain structure)

Called by:
  - scheduler.py schwab_data_job() at 4:00 PM ET, after schwab_fetch_all()
"""

import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import schwab.client
from sqlalchemy.orm import Session

from models.iv_history import IVHistory
from models.price_cache import PriceCache
from models.ticker import Ticker
import services.schwab_client as schwab_client_svc
from services.schwab_market_data import get_schwab_symbol

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# These tickers are excluded — indices have non-standard chain structure; futures use different chain APIs
IV_INELIGIBLE = {"VIX", "$DJI", "SPX", "NDX", "/CL", "/ZN", "/GC"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_iv_eligible_tickers(db: Session) -> list:
    rows = (
        db.query(Ticker)
        .filter(Ticker.active == True, Ticker.tier == 1)
        .order_by(Ticker.display_order)
        .all()
    )
    return [r.ticker for r in rows if r.ticker not in IV_INELIGIBLE]


def _compute_realized_vols(db: Session, ticker: str) -> tuple:
    """
    Compute 21-day and 63-day annualized realized vol from price_cache.history_json.
    Returns (rv21, rv63) as decimals (e.g. 0.196 = 19.6%), or (None, None) on error.
    """
    import json
    import numpy as np
    from models.price_cache import PriceCache as PC

    pc = db.query(PC).filter(PC.ticker == ticker).first()
    if not pc or not pc.history_json:
        return None, None

    closes = json.loads(pc.history_json)
    if len(closes) < 65:  # need at least 63 + 1 for returns
        return None, None

    arr  = np.array(closes, dtype=float)
    rets = np.log(arr[1:] / arr[:-1])

    rv21 = float(np.std(rets[-21:]) * (252 ** 0.5)) if len(rets) >= 21 else None
    rv63 = float(np.std(rets[-63:]) * (252 ** 0.5)) if len(rets) >= 63 else None

    return rv21, rv63


def _upsert_iv_history(
    db: Session, ticker: str, iv_date: str,
    implied_vol: float, rv21: float | None, rv63: float | None
) -> None:
    """Write one IV observation to iv_history (no commit — batch at end)."""
    vol_premium = round(implied_vol - rv21, 6) if rv21 is not None else None

    existing = db.query(IVHistory).filter(
        IVHistory.ticker  == ticker,
        IVHistory.iv_date == iv_date,
    ).first()
    if existing:
        existing.implied_vol = implied_vol
        existing.rv21        = rv21
        existing.rv63        = rv63
        existing.vol_premium = vol_premium
    else:
        db.add(IVHistory(
            ticker      = ticker,
            iv_date     = iv_date,
            implied_vol = implied_vol,
            rv21        = rv21,
            rv63        = rv63,
            vol_premium = vol_premium,
            created_at  = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        ))


def _atm_iv_for_exp(
    call_map: dict, put_map: dict, exp_key: str, underlying_price: float
) -> float | None:
    """
    Extract ATM implied vol for one expiration — averages call + put at ATM strike.
    Returns IV as a decimal (e.g. 0.318 for 31.8%).
    Guard: if Schwab returns percentage format (> 2.0), divides by 100.
    """
    strikes = call_map.get(exp_key, {})
    if not strikes:
        return None

    atm_strike = min(strikes.keys(), key=lambda s: abs(float(s) - underlying_price))

    ivs = []
    for side_map in [call_map, put_map]:
        opts = side_map.get(exp_key, {}).get(atm_strike, [])
        for opt in opts:
            vol = opt.get("volatility")
            if vol is not None:
                vol = float(vol)
                if vol > 0:
                    ivs.append(vol)

    if not ivs:
        return None

    iv = sum(ivs) / len(ivs)
    if iv > 2.0:
        iv = iv / 100.0
    return iv


def _extract_atm_iv(data: dict) -> float | None:
    """
    Extract 30-day constant-maturity implied volatility matching TOS methodology.

    Reads ATM IV from individual option contracts in callExpDateMap/putExpDateMap —
    NOT the top-level 'volatility' field (which is historical/realized vol).

    Strategy:
      - Parse all expirations >= 7 DTE (skip expiring weeklies)
      - Find the two expirations bracketing 30 DTE (near < 30, far >= 30)
      - Linearly interpolate ATM IV between them → constant 30-day IV
      - Fallback: if only one side of 30 DTE exists, use nearest available

    Returns IV as a decimal (e.g. 0.318 for 31.8%).
    """
    underlying_price = data.get("underlyingPrice")
    if not underlying_price:
        return None

    call_map = data.get("callExpDateMap", {})
    put_map  = data.get("putExpDateMap", {})

    if not call_map:
        return None

    # Parse all expirations >= 7 DTE — exp key format: "2026-04-18:12" (12 = DTE)
    expirations = []
    for exp_key in call_map:
        try:
            dte = int(exp_key.split(":")[1])
            if dte >= 7:
                expirations.append((dte, exp_key))
        except (IndexError, ValueError):
            continue

    if not expirations:
        return None

    expirations.sort()  # ascending DTE

    TARGET = 30

    near = [(dte, key) for dte, key in expirations if dte < TARGET]
    far  = [(dte, key) for dte, key in expirations if dte >= TARGET]

    if near and far:
        # Both sides of 30 DTE available — interpolate
        near_dte, near_key = near[-1]   # largest DTE still under 30
        far_dte,  far_key  = far[0]     # smallest DTE at or above 30

        near_iv = _atm_iv_for_exp(call_map, put_map, near_key, underlying_price)
        far_iv  = _atm_iv_for_exp(call_map, put_map, far_key,  underlying_price)

        if near_iv is not None and far_iv is not None:
            span = far_dte - near_dte
            iv = near_iv * (far_dte - TARGET) / span + far_iv * (TARGET - near_dte) / span
        else:
            iv = near_iv or far_iv  # one side failed — use whichever we have

    elif far:
        # All expirations >= 30 DTE — use nearest
        _, exp_key = far[0]
        iv = _atm_iv_for_exp(call_map, put_map, exp_key, underlying_price)

    else:
        # All expirations < 30 DTE — use nearest >= 7 DTE
        _, exp_key = near[-1]
        iv = _atm_iv_for_exp(call_map, put_map, exp_key, underlying_price)

    return round(iv, 6) if iv is not None else None


# Minimum iv_history observations required before IV Rank is meaningful.
# Below this threshold the min/max range is too narrow — proxy is used instead.
_IV_RANK_MIN_HISTORY = 30


def _compute_iv_percentile(db: Session, ticker: str, today_iv: float) -> int | None:
    """
    Compute IV Rank (0-100) matching TOS methodology.
    Formula: (current_iv - min_252) / (max_252 - min_252) * 100

    Returns None when fewer than _IV_RANK_MIN_HISTORY observations exist —
    caller should fall back to Yahoo realized vol proxy in that case.
    Today's row must already be flushed to iv_history before calling this.
    """
    history = (
        db.query(IVHistory)
        .filter(IVHistory.ticker == ticker)
        .order_by(IVHistory.iv_date.desc())
        .limit(252)
        .all()
    )
    iv_values = [row.implied_vol for row in history]
    if len(iv_values) < _IV_RANK_MIN_HISTORY:
        return None  # insufficient history — caller uses proxy

    iv_min = min(iv_values)
    iv_max = max(iv_values)
    if iv_max <= iv_min:
        return None

    rank = (today_iv - iv_min) / (iv_max - iv_min) * 100
    return max(0, min(100, int(round(rank))))


def _update_price_cache_iv(
    db: Session, ticker: str, iv_percentile: int, iv_source: str
) -> None:
    """Overwrite rel_iv and iv_source on the price_cache row (no commit)."""
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if row:
        row.rel_iv    = iv_percentile
        row.iv_source = iv_source


def _mark_proxy(db: Session, ticker: str) -> None:
    """Tag iv_source = 'proxy' without changing rel_iv (Yahoo proxy stays in place)."""
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if row and row.iv_source is None:
        row.iv_source = "proxy"


# ── Public entry point ────────────────────────────────────────────────────────

def schwab_fetch_iv(db: Session, force: bool = False) -> dict:
    """
    Fetch ATM IV from Schwab options chains for all IV-eligible Tier 1 tickers.
    Rate: ~47 calls at 0.5s delay ≈ 24 seconds.
    Total daily requests with price fetch: ~99 (well under 120/min limit).

    force=True bypasses the idempotency check — used by manual REFRESH DATA so
    intraday refreshes always get fresh IV, not just the first run of the day.
    """
    today    = datetime.now(_ET).strftime("%Y-%m-%d")
    eligible = _get_iv_eligible_tickers(db)

    if not eligible:
        return {"fetched": 0, "errors": 0}

    # Idempotency check — skip if already fetched today (scheduler path only)
    if not force:
        sample = db.query(IVHistory).filter(
            IVHistory.ticker  == eligible[0],
            IVHistory.iv_date == today,
        ).first()
        if sample:
            logger.info("IV: already fetched today — skipping")
            return {"fetched": len(eligible), "errors": 0}

    # Build Schwab client
    try:
        client = schwab_client_svc.get_schwab_client(db)
    except RuntimeError:
        logger.info("IV: no Schwab tokens — tagging all tickers as proxy")
        for ticker in eligible:
            _mark_proxy(db, ticker)
        db.commit()
        return {"fetched": 0, "errors": 0, "data_source": "proxy"}

    OC = schwab.client.Client.Options

    fetched = 0
    errors  = 0

    for ticker in eligible:
        schwab_sym = get_schwab_symbol(ticker)
        try:
            resp = client.get_option_chain(
                schwab_sym,
                contract_type           = OC.ContractType.ALL,
                strike_count            = 1,
                include_underlying_quote = False,
            )
            resp.raise_for_status()
            data        = resp.json()
            implied_vol = _extract_atm_iv(data)

            if implied_vol is None or implied_vol <= 0:
                logger.warning(f"IV: no valid ATM IV for {ticker} ({schwab_sym})")
                _mark_proxy(db, ticker)
                errors += 1
                time.sleep(0.5)
                continue

            # Compute realized vols for logging alongside implied vol
            rv21, rv63 = _compute_realized_vols(db, ticker)

            # Write to iv_history first (today's value included in percentile calc)
            _upsert_iv_history(db, ticker, today, implied_vol, rv21, rv63)
            db.flush()  # make row visible within same session for percentile query

            # Compute IV Rank — returns None if history < _IV_RANK_MIN_HISTORY days
            iv_pct = _compute_iv_percentile(db, ticker, implied_vol)

            if iv_pct is not None:
                # Sufficient history — use real IV Rank
                _update_price_cache_iv(db, ticker, iv_pct, iv_source="schwab")
            else:
                # Warmup period — fall back to Yahoo realized vol proxy so rel_iv
                # shows a meaningful number while iv_history accumulates
                import json
                import pandas as pd
                from services.yahoo_finance import compute_realized_vol_percentile
                pc_row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
                if pc_row and pc_row.history_json:
                    closes = pd.Series(json.loads(pc_row.history_json))
                    proxy_pct = compute_realized_vol_percentile(closes)
                else:
                    proxy_pct = 50
                _update_price_cache_iv(db, ticker, proxy_pct, iv_source="proxy")
                logger.debug(f"IV: {ticker} warmup — using proxy rel_iv={proxy_pct}")

            fetched += 1
            logger.debug(f"IV: {ticker} vol={implied_vol:.4f} pct={iv_pct}")

        except Exception as e:
            logger.warning(f"IV fetch failed for {ticker} ({schwab_sym}): {e} — using proxy")
            _mark_proxy(db, ticker)
            errors += 1

        time.sleep(0.5)

    db.commit()
    logger.info(f"IV fetch complete: {fetched} fetched, {errors} errors")
    return {"fetched": fetched, "errors": errors}
