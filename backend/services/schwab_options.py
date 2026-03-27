"""
schwab_options.py — Schwab options chain IV fetch.

Entry point: schwab_fetch_iv(db)
  - Fetches ATM implied volatility for IV-eligible tickers via Schwab options chains
  - Writes daily IV to iv_history table
  - Computes IV Percentile (0-100) from rolling 252-day iv_history
  - Updates price_cache.rel_iv + price_cache.iv_source
  - Falls back to existing Yahoo proxy (iv_source = 'proxy') per ticker on any error
  - Idempotent within a trading day

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
from scipy.stats import percentileofscore
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


def _upsert_iv_history(db: Session, ticker: str, iv_date: str, implied_vol: float) -> None:
    """Write one IV observation to iv_history (no commit — batch at end)."""
    existing = db.query(IVHistory).filter(
        IVHistory.ticker  == ticker,
        IVHistory.iv_date == iv_date,
    ).first()
    if existing:
        existing.implied_vol = implied_vol
    else:
        db.add(IVHistory(
            ticker      = ticker,
            iv_date     = iv_date,
            implied_vol = implied_vol,
            created_at  = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        ))


def _compute_iv_percentile(db: Session, ticker: str, today_iv: float) -> int:
    """
    Compute IV Percentile (0-100) for today's IV relative to rolling 252-day history.
    Today's row must already be written to iv_history before calling this.
    Returns 50 when fewer than 5 observations are available (cold start).
    """
    history = (
        db.query(IVHistory)
        .filter(IVHistory.ticker == ticker)
        .order_by(IVHistory.iv_date.desc())
        .limit(252)
        .all()
    )
    iv_values = [row.implied_vol for row in history]
    if len(iv_values) < 5:
        return 50  # insufficient history — default to midpoint
    pct = percentileofscore(iv_values, today_iv, kind="rank")
    return max(0, min(100, int(pct)))


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

def schwab_fetch_iv(db: Session) -> dict:
    """
    Fetch ATM IV from Schwab options chains for all IV-eligible Tier 1 tickers.
    Rate: ~47 calls at 0.5s delay ≈ 24 seconds.
    Total daily requests with price fetch: ~99 (well under 120/min limit).
    """
    today    = datetime.now(_ET).strftime("%Y-%m-%d")
    eligible = _get_iv_eligible_tickers(db)

    if not eligible:
        return {"fetched": 0, "errors": 0}

    # Idempotency check — skip if already fetched today
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
            data    = resp.json()
            raw_vol = data.get("volatility")

            if raw_vol is None or float(raw_vol) <= 0:
                logger.warning(f"IV: no valid volatility for {ticker} ({schwab_sym})")
                _mark_proxy(db, ticker)
                errors += 1
                time.sleep(0.5)
                continue

            # Schwab returns volatility as a percentage (e.g. 18.7 = 18.7% IV)
            # Store as decimal to match spec: 18.7 → 0.187
            implied_vol = round(float(raw_vol) / 100.0, 6)

            # Write to iv_history first (today's value included in percentile calc)
            _upsert_iv_history(db, ticker, today, implied_vol)
            db.flush()  # make row visible within same session for percentile query

            # Compute percentile against rolling 252-day history
            iv_pct = _compute_iv_percentile(db, ticker, implied_vol)

            # Update price_cache
            _update_price_cache_iv(db, ticker, iv_pct, iv_source="schwab")

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
