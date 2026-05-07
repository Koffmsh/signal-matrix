"""
schwab_options.py — Schwab options chain IV fetch.

Entry point: schwab_fetch_iv(db)
  - Fetches ATM IV30 + 25Δ skew + put/call ratio for IV-eligible tickers
  - Writes daily record to vol_history table
  - Computes IV Rank and Skew Rank (0-100) matching TOS methodology
  - Updates price_cache: rel_iv, iv30, risk_reversal, skew_rank, put_call_ratio, iv_source
  - Falls back to existing Yahoo proxy (iv_source = 'proxy') per ticker on any error
  - Idempotent within a trading day

IV source: ATM option contracts in callExpDateMap/putExpDateMap — NOT the top-level
  'volatility' field, which is historical/realized vol, not implied vol.

IV-eligible: all active Tier 1 tickers EXCEPT VIX, $DJI, SPX, NDX, RUT, VVIX, and futures
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

from models.vol_history import VolHistory
from models.price_cache import PriceCache
from models.ticker import Ticker
import services.schwab_client as schwab_client_svc
from services.schwab_market_data import get_schwab_symbol

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# These tickers are excluded — indices have non-standard chain structure; futures use different chain APIs
IV_INELIGIBLE = {"VIX", "$DJI", "SPX", "NDX", "RUT", "/CL", "/ZN", "/GC", "VVIX"}

# Minimum vol_history observations required before ranks are meaningful.
_RANK_MIN_HISTORY = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_iv_eligible_tickers(db: Session) -> list:
    rows = (
        db.query(Ticker)
        .filter(Ticker.active == True, Ticker.tier == 1)
        .order_by(Ticker.display_order)
        .all()
    )
    return [r.ticker for r in rows if r.ticker not in IV_INELIGIBLE]


def _compute_hv(db: Session, ticker: str) -> tuple:
    """
    Compute HV30 and HV90 annualized realized vol from price_cache.history_json.
    HV30 = std of last 21 log returns × √252  (≈ 30 calendar days)
    HV90 = std of last 63 log returns × √252  (≈ 90 calendar days)
    Returns (hv30, hv90) as decimals (e.g. 0.196 = 19.6%), or (None, None) on error.
    """
    import json
    import numpy as np

    pc = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if not pc or not pc.history_json:
        return None, None

    closes = json.loads(pc.history_json)
    if len(closes) < 65:  # need at least 63 + 1 for returns
        return None, None

    arr  = np.array(closes, dtype=float)
    rets = np.log(arr[1:] / arr[:-1])

    hv30 = round(float(np.std(rets[-21:], ddof=0) * (252 ** 0.5)), 6) if len(rets) >= 21 else None
    hv90 = round(float(np.std(rets[-63:], ddof=0) * (252 ** 0.5)), 6) if len(rets) >= 63 else None

    return hv30, hv90


def _normalize_iv(vol) -> float | None:
    """Ensure IV is in decimal form (e.g. 0.20 not 20.0). Guard: >2.0 → divide by 100."""
    if vol is None:
        return None
    vol = float(vol)
    if vol <= 0:
        return None
    return vol / 100.0 if vol > 2.0 else vol


def _atm_iv_for_exp(
    call_map: dict, put_map: dict, exp_key: str, underlying_price: float
) -> float | None:
    """
    Extract ATM implied vol for one expiration — averages call + put at ATM strike.
    Returns IV as a decimal (e.g. 0.318 for 31.8%).
    """
    strikes = call_map.get(exp_key, {})
    if not strikes:
        return None

    atm_strike = min(strikes.keys(), key=lambda s: abs(float(s) - underlying_price))

    ivs = []
    for side_map in [call_map, put_map]:
        opts = side_map.get(exp_key, {}).get(atm_strike, [])
        for opt in opts:
            v = _normalize_iv(opt.get("volatility"))
            if v is not None:
                ivs.append(v)

    return sum(ivs) / len(ivs) if ivs else None


def _select_30d_expirations(call_map: dict) -> tuple:
    """
    Parse all expirations >= 7 DTE and return bracket around 30 DTE.
    Returns (near_dte, near_key, far_dte, far_key) — any element may be None.
    """
    expirations = []
    for exp_key in call_map:
        try:
            dte = int(exp_key.split(":")[1])
            if dte >= 7:
                expirations.append((dte, exp_key))
        except (IndexError, ValueError):
            continue

    if not expirations:
        return None, None, None, None

    expirations.sort()
    TARGET = 30
    near_list = [(d, k) for d, k in expirations if d < TARGET]
    far_list  = [(d, k) for d, k in expirations if d >= TARGET]

    near_dte, near_key = near_list[-1] if near_list else (None, None)
    far_dte,  far_key  = far_list[0]   if far_list  else (None, None)

    return near_dte, near_key, far_dte, far_key


def _extract_atm_iv(data: dict) -> float | None:
    """
    Extract 30-day constant-maturity implied volatility matching TOS methodology.
    Linearly interpolates between the two expirations bracketing 30 DTE.
    Returns IV as a decimal (e.g. 0.318 for 31.8%).
    """
    underlying_price = data.get("underlyingPrice")
    if not underlying_price:
        return None

    call_map = data.get("callExpDateMap", {})
    put_map  = data.get("putExpDateMap", {})
    if not call_map:
        return None

    near_dte, near_key, far_dte, far_key = _select_30d_expirations(call_map)

    if near_key and far_key:
        near_iv = _atm_iv_for_exp(call_map, put_map, near_key, underlying_price)
        far_iv  = _atm_iv_for_exp(call_map, put_map, far_key,  underlying_price)
        if near_iv is not None and far_iv is not None:
            span = far_dte - near_dte
            iv = near_iv * (far_dte - 30) / span + far_iv * (30 - near_dte) / span
        else:
            iv = near_iv or far_iv
    elif far_key:
        iv = _atm_iv_for_exp(call_map, put_map, far_key, underlying_price)
    elif near_key:
        iv = _atm_iv_for_exp(call_map, put_map, near_key, underlying_price)
    else:
        return None

    return round(iv, 6) if iv is not None else None


def _extract_put_call_ratio(data: dict) -> float | None:
    """
    Compute put/call ratio from open interest across the full fetched chain.
    P/C > 1.0 = more put OI than call OI = fear / hedging.
    P/C < 0.6 = call-heavy = complacency or bullish positioning.
    """
    call_map = data.get("callExpDateMap", {})
    put_map  = data.get("putExpDateMap", {})

    total_call_oi = 0
    total_put_oi  = 0

    for strikes in call_map.values():
        for opts in strikes.values():
            for opt in opts:
                oi = opt.get("openInterest")
                if oi:
                    total_call_oi += int(oi)

    for strikes in put_map.values():
        for opts in strikes.values():
            for opt in opts:
                oi = opt.get("openInterest")
                if oi:
                    total_put_oi += int(oi)

    if total_call_oi == 0:
        return None

    return round(total_put_oi / total_call_oi, 4)


def _upsert_vol_history(
    db: Session, ticker: str, iv_date: str,
    implied_vol: float, hv30: float | None, hv90: float | None,
    call_iv_25d: float | None, put_iv_25d: float | None,
    risk_reversal: float | None, put_call_ratio: float | None,
) -> None:
    """Write one IV observation to vol_history (no commit — batch at end)."""
    vrp = round(implied_vol - hv30, 6) if (implied_vol is not None and hv30 is not None) else None

    existing = db.query(VolHistory).filter(
        VolHistory.ticker  == ticker,
        VolHistory.iv_date == iv_date,
    ).first()
    if existing:
        existing.implied_vol    = implied_vol
        existing.hv30           = hv30
        existing.hv90           = hv90
        existing.vrp            = vrp
        existing.call_iv_25d    = call_iv_25d
        existing.put_iv_25d     = put_iv_25d
        existing.risk_reversal  = risk_reversal
        existing.put_call_ratio = put_call_ratio
    else:
        db.add(VolHistory(
            ticker          = ticker,
            iv_date         = iv_date,
            implied_vol     = implied_vol,
            hv30            = hv30,
            hv90            = hv90,
            vrp             = vrp,
            call_iv_25d     = call_iv_25d,
            put_iv_25d      = put_iv_25d,
            risk_reversal   = risk_reversal,
            put_call_ratio  = put_call_ratio,
            created_at      = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        ))


def _compute_iv_percentile(db: Session, ticker: str, today_iv: float) -> int | None:
    """
    Compute IV Rank (0-100) matching TOS methodology.
    Formula: (current_iv - min_252) / (max_252 - min_252) * 100
    Returns None when fewer than _RANK_MIN_HISTORY observations exist.
    Today's row must already be flushed before calling this.
    """
    history = (
        db.query(VolHistory)
        .filter(VolHistory.ticker == ticker, VolHistory.implied_vol.isnot(None))
        .order_by(VolHistory.iv_date.desc())
        .limit(252)
        .all()
    )
    iv_values = [row.implied_vol for row in history]
    if len(iv_values) < _RANK_MIN_HISTORY:
        return None

    iv_min = min(iv_values)
    iv_max = max(iv_values)
    if iv_max <= iv_min:
        return None

    rank = (today_iv - iv_min) / (iv_max - iv_min) * 100
    return max(0, min(100, int(round(rank))))


def _compute_skew_rank(db: Session, ticker: str, today_rr: float) -> int | None:
    """
    Compute Skew Rank (0-100) — risk reversal rank within its own 252-day history.
    Low rank = puts historically cheap relative to calls = bullish tailwind.
    High rank = puts expensive relative to calls = fear / bearish signal.
    Returns None when fewer than _RANK_MIN_HISTORY observations exist.
    Today's row must already be flushed before calling this.
    """
    history = (
        db.query(VolHistory)
        .filter(VolHistory.ticker == ticker, VolHistory.risk_reversal.isnot(None))
        .order_by(VolHistory.iv_date.desc())
        .limit(252)
        .all()
    )
    rr_values = [row.risk_reversal for row in history]
    if len(rr_values) < _RANK_MIN_HISTORY:
        return None

    rr_min = min(rr_values)
    rr_max = max(rr_values)
    if rr_max <= rr_min:
        return None

    rank = (today_rr - rr_min) / (rr_max - rr_min) * 100
    return max(0, min(100, int(round(rank))))


def _compute_vrp_rank(db: Session, ticker: str, today_vrp: float) -> int | None:
    """
    Compute VRP Rank (0-100) — vol risk premium rank within its own 252-day history.
    High rank = IV expensive vs realized (historically elevated premium) = red.
    Low rank  = IV cheap vs realized = green (options underpriced vs actual moves).
    Returns None when fewer than _RANK_MIN_HISTORY observations exist.
    Today's row must already be flushed before calling this.
    """
    history = (
        db.query(VolHistory)
        .filter(VolHistory.ticker == ticker, VolHistory.vrp.isnot(None))
        .order_by(VolHistory.iv_date.desc())
        .limit(252)
        .all()
    )
    vrp_values = [row.vrp for row in history]
    if len(vrp_values) < _RANK_MIN_HISTORY:
        return None

    vrp_min = min(vrp_values)
    vrp_max = max(vrp_values)
    if vrp_max <= vrp_min:
        return None

    rank = (today_vrp - vrp_min) / (vrp_max - vrp_min) * 100
    return max(0, min(100, int(round(rank))))


def _compute_hv_rank(db: Session, ticker: str, today_hv30: float) -> int | None:
    """
    Compute HV Rank (0-100) — HV30 rank within its own 252-day history.
    Low rank = realized vol historically low (calm); high rank = vol historically elevated.
    Returns None when fewer than _RANK_MIN_HISTORY observations exist.
    Today's row must already be flushed before calling this.
    """
    history = (
        db.query(VolHistory)
        .filter(VolHistory.ticker == ticker, VolHistory.hv30.isnot(None))
        .order_by(VolHistory.iv_date.desc())
        .limit(252)
        .all()
    )
    hv_values = [row.hv30 for row in history]
    if len(hv_values) < _RANK_MIN_HISTORY:
        return None

    hv_min = min(hv_values)
    hv_max = max(hv_values)
    if hv_max <= hv_min:
        return None

    rank = (today_hv30 - hv_min) / (hv_max - hv_min) * 100
    return max(0, min(100, int(round(rank))))


def _compute_vrp_changes(db: Session, ticker: str) -> tuple:
    """
    Compute VRP change over 1 trading day, 1 week (5 days), 1 month (21 days).
    Queries the last 22 vol_history rows with valid VRP (today already flushed).
    Returns (vrp_1d_chg, vrp_1w_chg, vrp_1m_chg) as decimals — any may be None.
    """
    rows = (
        db.query(VolHistory)
        .filter(VolHistory.ticker == ticker, VolHistory.vrp.isnot(None))
        .order_by(VolHistory.iv_date.desc())
        .limit(22)
        .all()
    )
    if not rows:
        return None, None, None

    today_vrp = rows[0].vrp

    def _chg(idx: int):
        return round(today_vrp - rows[idx].vrp, 6) if len(rows) > idx else None

    return _chg(1), _chg(5), _chg(21)


def _update_price_cache_iv(
    db: Session, ticker: str,
    iv_percentile: int, iv_source: str,
    iv30: float | None = None,
    hv30: float | None = None,
    hv90: float | None = None,
    risk_reversal: float | None = None,
    skew_rank: int | None = None,
    put_call_ratio: float | None = None,
    vrp_rank: int | None = None,
    hv_rank: int | None = None,
    vrp_1d_chg: float | None = None,
    vrp_1w_chg: float | None = None,
    vrp_1m_chg: float | None = None,
) -> None:
    """Overwrite all volatility fields on the price_cache row (no commit)."""
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if row:
        row.rel_iv         = iv_percentile
        row.iv_source      = iv_source
        row.iv30           = iv30
        row.hv30           = hv30
        row.hv90           = hv90
        row.risk_reversal  = risk_reversal
        row.skew_rank      = skew_rank
        row.put_call_ratio = put_call_ratio
        row.vrp_rank       = vrp_rank
        row.hv_rank        = hv_rank
        row.vrp_1d_chg     = vrp_1d_chg
        row.vrp_1w_chg     = vrp_1w_chg
        row.vrp_1m_chg     = vrp_1m_chg


def _mark_proxy(db: Session, ticker: str) -> None:
    """Tag iv_source = 'proxy' without changing rel_iv (Yahoo proxy stays in place)."""
    row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if row and row.iv_source is None:
        row.iv_source = "proxy"


# ── Public entry point ────────────────────────────────────────────────────────

def schwab_fetch_iv(db: Session, force: bool = False) -> dict:
    """
    Fetch ATM IV30 + 25Δ skew + put/call ratio for all IV-eligible Tier 1 tickers.
    strike_count=20 captures OTM strikes needed for 25-delta options on most tickers.
    Rate: ~47 calls at 0.5s delay ≈ 24 seconds.

    force=False (default): idempotent — skips if already fetched today.
    """
    today    = datetime.now(_ET).strftime("%Y-%m-%d")
    eligible = _get_iv_eligible_tickers(db)

    if not eligible:
        return {"fetched": 0, "errors": 0}

    # Idempotency check — skip if already fetched today
    if not force:
        sample = db.query(VolHistory).filter(
            VolHistory.ticker  == eligible[0],
            VolHistory.iv_date == today,
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
                contract_type            = OC.ContractType.ALL,
                strike_count             = 5,    # ATM IV only — 5 strikes each side is sufficient
                include_underlying_quote = False,
            )
            resp.raise_for_status()
            data = resp.json()

            implied_vol = _extract_atm_iv(data)
            if implied_vol is None or implied_vol <= 0:
                logger.warning(f"IV: no valid ATM IV for {ticker} ({schwab_sym})")
                _mark_proxy(db, ticker)
                errors += 1
                time.sleep(0.5)
                continue

            # Compute HV30/HV90 from price history
            hv30, hv90 = _compute_hv(db, ticker)

            # Skew dropped — always null (Option A: columns remain, data not populated)
            call_iv_25d = put_iv_25d = risk_reversal = None
            put_call_ratio = _extract_put_call_ratio(data)

            # Compute VRP = IV30 - HV30
            vrp = round(implied_vol - hv30, 6) if (implied_vol is not None and hv30 is not None) else None

            # Write to vol_history (today's row included in rank calcs)
            _upsert_vol_history(
                db, ticker, today, implied_vol, hv30, hv90,
                call_iv_25d, put_iv_25d, risk_reversal, put_call_ratio,
            )
            db.flush()

            # Compute IV Rank, VRP Rank, HV Rank (skew_rank dropped with skew)
            iv_pct   = _compute_iv_percentile(db, ticker, implied_vol)
            vrp_rank = _compute_vrp_rank(db, ticker, vrp) if vrp is not None else None
            hv_rank  = _compute_hv_rank(db, ticker, hv30) if hv30 is not None else None

            # Compute VRP changes (1d, 1w, 1m) from vol_history
            vrp_1d_chg, vrp_1w_chg, vrp_1m_chg = _compute_vrp_changes(db, ticker)

            if iv_pct is not None:
                _update_price_cache_iv(
                    db, ticker, iv_pct, "schwab",
                    iv30=implied_vol, hv30=hv30, hv90=hv90,
                    put_call_ratio=put_call_ratio,
                    vrp_rank=vrp_rank, hv_rank=hv_rank,
                    vrp_1d_chg=vrp_1d_chg, vrp_1w_chg=vrp_1w_chg, vrp_1m_chg=vrp_1m_chg,
                )
            else:
                # Warmup — fall back to Yahoo proxy for rel_iv display
                import json
                import pandas as pd
                from services.yahoo_finance import compute_realized_vol_percentile
                pc_row = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
                proxy_pct = 50
                if pc_row and pc_row.history_json:
                    closes = pd.Series(json.loads(pc_row.history_json))
                    proxy_pct = compute_realized_vol_percentile(closes)
                _update_price_cache_iv(
                    db, ticker, proxy_pct, "proxy",
                    iv30=implied_vol, hv30=hv30, hv90=hv90,
                    put_call_ratio=put_call_ratio,
                    vrp_rank=vrp_rank, hv_rank=hv_rank,
                    vrp_1d_chg=vrp_1d_chg, vrp_1w_chg=vrp_1w_chg, vrp_1m_chg=vrp_1m_chg,
                )
                logger.debug(f"IV: {ticker} warmup — using proxy rel_iv={proxy_pct}")

            fetched += 1
            logger.debug(
                f"IV: {ticker} iv={implied_vol:.4f} hv30={hv30} vrp={vrp} "
                f"vrp_1d={vrp_1d_chg} vrp_1w={vrp_1w_chg} vrp_1m={vrp_1m_chg} "
                f"pcr={put_call_ratio} iv_pct={iv_pct} vrp_rank={vrp_rank} hv_rank={hv_rank}"
            )

        except Exception as e:
            logger.warning(f"IV fetch failed for {ticker} ({schwab_sym}): {e} — using proxy")
            _mark_proxy(db, ticker)
            errors += 1

        time.sleep(0.5)

    db.commit()
    logger.info(f"IV fetch complete: {fetched} fetched, {errors} errors")
    return {"fetched": fetched, "errors": errors}


# Tickers that route through Yahoo (no Schwab price quote) — HV accumulated daily from price history
_HV_ONLY_TICKERS = {"SPX", "NDX", "RUT", "VIX", "$DJI", "USD", "JPY", "/CL", "/ZN", "/GC", "VVIX"}


def accumulate_hv_only(db: Session) -> dict:
    """
    Compute and store HV30/HV90 in vol_history for Yahoo-only tickers that never
    go through schwab_fetch_iv(). Called daily after the main IV fetch job.
    implied_vol and all IV-derived fields (vrp, skew, etc.) are left NULL.
    """
    import json
    import numpy as np

    today = datetime.now(_ET).strftime("%Y-%m-%d")
    written = 0
    skipped = 0

    for ticker in sorted(_HV_ONLY_TICKERS):
        try:
            pc = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
            if not pc or not pc.history_json:
                logger.debug(f"HV-only: {ticker} — no price history, skipping")
                continue

            closes = json.loads(pc.history_json)
            if len(closes) < 22:
                logger.debug(f"HV-only: {ticker} — insufficient history ({len(closes)} bars)")
                continue

            arr  = np.array(closes, dtype=float)
            rets = np.log(arr[1:] / arr[:-1])
            hv30 = round(float(np.std(rets[-21:], ddof=0) * (252 ** 0.5)), 6) if len(rets) >= 21 else None
            hv90 = round(float(np.std(rets[-63:], ddof=0) * (252 ** 0.5)), 6) if len(rets) >= 63 else None

            existing = db.query(VolHistory).filter(
                VolHistory.ticker  == ticker,
                VolHistory.iv_date == today,
            ).first()

            if existing:
                existing.hv30 = hv30
                existing.hv90 = hv90
                skipped += 1
            else:
                db.add(VolHistory(
                    ticker      = ticker,
                    iv_date     = today,
                    implied_vol = None,
                    hv30        = hv30,
                    hv90        = hv90,
                    created_at  = datetime.utcnow().isoformat(),
                ))
                written += 1
            db.flush()

            # Stamp current values onto price_cache (popup display + Trade RR consumer)
            hv_rank = _compute_hv_rank(db, ticker, hv30) if hv30 is not None else None
            pc.hv30    = hv30
            pc.hv90    = hv90
            pc.hv_rank = hv_rank

        except Exception as e:
            logger.error(f"HV-only accumulation failed for {ticker}: {e}")

    db.commit()
    logger.info(f"HV-only accumulation complete: {written} new, {skipped} updated")
    return {"written": written, "skipped": skipped}
