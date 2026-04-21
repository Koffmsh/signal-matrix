"""
schwab_options.py — Schwab options chain IV fetch.

Entry point: schwab_fetch_iv(db)
  - Fetches ATM IV30 + 25Δ skew + put/call ratio for IV-eligible tickers
  - Writes daily record to iv_history table
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

from models.iv_history import IVHistory
from models.price_cache import PriceCache
from models.ticker import Ticker
import services.schwab_client as schwab_client_svc
from services.schwab_market_data import get_schwab_symbol

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# These tickers are excluded — indices have non-standard chain structure; futures use different chain APIs
IV_INELIGIBLE = {"VIX", "$DJI", "SPX", "NDX", "RUT", "/CL", "/ZN", "/GC", "VVIX"}

# Minimum iv_history observations required before ranks are meaningful.
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


def _extract_25d_skew(data: dict) -> tuple:
    """
    Extract 25-delta call and put IV at 30-day constant maturity.
    Uses the same expiration interpolation as _extract_atm_iv.

    25Δ call: contract with delta closest to +0.25 (OTM call)
    25Δ put:  contract with delta closest to -0.25 (OTM put)

    Risk Reversal = call_iv_25d - put_iv_25d
      Positive = forward skew = institutional call buying = bullish signal
      Negative = normal smirk = downside protection bid (typical for equities)

    Returns (call_iv_25d, put_iv_25d, risk_reversal) as decimals, or (None, None, None).
    Requires strike_count >= 10 on the chain fetch to reliably find 25Δ strikes.
    """
    underlying_price = data.get("underlyingPrice")
    if not underlying_price:
        return None, None, None

    call_map = data.get("callExpDateMap", {})
    put_map  = data.get("putExpDateMap", {})
    if not call_map:
        return None, None, None

    near_dte, near_key, far_dte, far_key = _select_30d_expirations(call_map)

    def _25d_ivs_for_exp(exp_key: str) -> tuple:
        """Find 25Δ call and put IVs for one expiration using delta field."""
        call_strikes = call_map.get(exp_key, {})
        put_strikes  = put_map.get(exp_key, {})

        best_call_iv, best_call_dist = None, float("inf")
        for strike, opts in call_strikes.items():
            for opt in opts:
                d = opt.get("delta")
                if d is None:
                    continue
                d = float(d)
                if d <= 0 or d >= 1:
                    continue  # skip ITM or invalid
                dist = abs(d - 0.25)
                if dist < best_call_dist:
                    iv = _normalize_iv(opt.get("volatility"))
                    if iv is not None:
                        best_call_iv   = iv
                        best_call_dist = dist

        best_put_iv, best_put_dist = None, float("inf")
        for strike, opts in put_strikes.items():
            for opt in opts:
                d = opt.get("delta")
                if d is None:
                    continue
                d = float(d)
                if d >= 0 or d <= -1:
                    continue  # skip ITM or invalid
                dist = abs(d - (-0.25))
                if dist < best_put_dist:
                    iv = _normalize_iv(opt.get("volatility"))
                    if iv is not None:
                        best_put_iv   = iv
                        best_put_dist = dist

        return best_call_iv, best_put_iv

    if near_key and far_key:
        near_call, near_put = _25d_ivs_for_exp(near_key)
        far_call,  far_put  = _25d_ivs_for_exp(far_key)
        span = far_dte - near_dte
        if near_call is not None and far_call is not None:
            call_iv = near_call * (far_dte - 30) / span + far_call * (30 - near_dte) / span
        else:
            call_iv = near_call or far_call
        if near_put is not None and far_put is not None:
            put_iv = near_put * (far_dte - 30) / span + far_put * (30 - near_dte) / span
        else:
            put_iv = near_put or far_put
    elif far_key:
        call_iv, put_iv = _25d_ivs_for_exp(far_key)
    elif near_key:
        call_iv, put_iv = _25d_ivs_for_exp(near_key)
    else:
        return None, None, None

    if call_iv is None or put_iv is None:
        return None, None, None

    call_iv = round(call_iv, 6)
    put_iv  = round(put_iv, 6)
    rr      = round(call_iv - put_iv, 6)

    return call_iv, put_iv, rr


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


def _upsert_iv_history(
    db: Session, ticker: str, iv_date: str,
    implied_vol: float, hv30: float | None, hv90: float | None,
    call_iv_25d: float | None, put_iv_25d: float | None,
    risk_reversal: float | None, put_call_ratio: float | None,
) -> None:
    """Write one IV observation to iv_history (no commit — batch at end)."""
    vrp = round(implied_vol - hv30, 6) if (implied_vol is not None and hv30 is not None) else None

    existing = db.query(IVHistory).filter(
        IVHistory.ticker  == ticker,
        IVHistory.iv_date == iv_date,
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
        db.add(IVHistory(
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
        db.query(IVHistory)
        .filter(IVHistory.ticker == ticker, IVHistory.implied_vol.isnot(None))
        .order_by(IVHistory.iv_date.desc())
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
        db.query(IVHistory)
        .filter(IVHistory.ticker == ticker, IVHistory.risk_reversal.isnot(None))
        .order_by(IVHistory.iv_date.desc())
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
        db.query(IVHistory)
        .filter(IVHistory.ticker == ticker, IVHistory.vrp.isnot(None))
        .order_by(IVHistory.iv_date.desc())
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
                contract_type            = OC.ContractType.ALL,
                strike_count             = 20,   # 20 strikes each side — captures 25Δ options
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

            # Extract 25Δ skew and put/call ratio from same chain response
            call_iv_25d, put_iv_25d, risk_reversal = _extract_25d_skew(data)
            put_call_ratio = _extract_put_call_ratio(data)

            # Compute VRP = IV30 - HV30
            vrp = round(implied_vol - hv30, 6) if (implied_vol is not None and hv30 is not None) else None

            # Write to iv_history (today's row included in rank calcs)
            _upsert_iv_history(
                db, ticker, today, implied_vol, hv30, hv90,
                call_iv_25d, put_iv_25d, risk_reversal, put_call_ratio,
            )
            db.flush()

            # Compute IV Rank, Skew Rank, and VRP Rank
            iv_pct    = _compute_iv_percentile(db, ticker, implied_vol)
            skew_rank = _compute_skew_rank(db, ticker, risk_reversal) if risk_reversal is not None else None
            vrp_rank  = _compute_vrp_rank(db, ticker, vrp) if vrp is not None else None

            if iv_pct is not None:
                _update_price_cache_iv(
                    db, ticker, iv_pct, "schwab",
                    iv30=implied_vol, hv30=hv30, hv90=hv90,
                    risk_reversal=risk_reversal,
                    skew_rank=skew_rank, put_call_ratio=put_call_ratio,
                    vrp_rank=vrp_rank,
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
                    risk_reversal=risk_reversal,
                    skew_rank=skew_rank, put_call_ratio=put_call_ratio,
                    vrp_rank=vrp_rank,
                )
                logger.debug(f"IV: {ticker} warmup — using proxy rel_iv={proxy_pct}")

            fetched += 1
            logger.debug(
                f"IV: {ticker} iv={implied_vol:.4f} hv30={hv30} vrp={vrp} rr={risk_reversal} "
                f"pcr={put_call_ratio} iv_pct={iv_pct} vrp_rank={vrp_rank}"
            )

        except Exception as e:
            logger.warning(f"IV fetch failed for {ticker} ({schwab_sym}): {e} — using proxy")
            _mark_proxy(db, ticker)
            errors += 1

        time.sleep(0.5)

    db.commit()
    logger.info(f"IV fetch complete: {fetched} fetched, {errors} errors")
    return {"fetched": fetched, "errors": errors}
