"""
spx_constituents.py — SPX constituent weights + daily impact calculation.

Data source: iShares IVV holdings CSV (public, no auth required).
IVV tracks the S&P 500 index with constituent weights updated daily.

EOD flow (called from scheduler after calculate_signals):
  1. Fetch IVV holdings CSV → {ticker: weight_pct}
  2. Batch quote all ~503 constituents via Schwab
  3. Compute contribution = daily_return_pct × (weight_pct / 100)
  4. Store top 10 contributors + detractors in spx_impact_cache table

The result is a read-only endpoint — no manual trigger needed.
"""

import csv
import io
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

import services.schwab_client as schwab_client_svc
from models.spx_impact_cache import SpxImpactCache

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# iShares IVV (Core S&P 500 ETF) holdings — public download, no auth required
# CSV updated daily by iShares; contains all ~503 SPX constituents with weights
_IVV_HOLDINGS_URL = (
    "https://www.ishares.com/us/products/239726/"
    "ishares-core-sp-500-etf/1467271812596.ajax"
    "?fileType=csv&fileName=IVV_holdings&dataType=fund"
)

_TOP_N = 10


def fetch_spx_weights() -> dict:
    """
    Download IVV holdings CSV and return {ticker: weight_pct} for equity constituents.
    Raises on network or parse failure.
    """
    resp = httpx.get(
        _IVV_HOLDINGS_URL,
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()

    lines = resp.text.splitlines()

    # iShares CSV has metadata rows before the actual column header.
    # Find the header row by locating "Ticker" as a field name.
    data_start = None
    for i, line in enumerate(lines):
        first_field = line.split(",")[0].strip().strip('"')
        if first_field == "Ticker":
            data_start = i
            break

    if data_start is None:
        raise ValueError("Could not locate 'Ticker' header row in IVV holdings CSV")

    weights = {}
    reader = csv.DictReader(io.StringIO("\n".join(lines[data_start:])))
    for row in reader:
        ticker     = row.get("Ticker", "").strip().upper()
        weight_str = row.get("Weight (%)", "").strip()
        asset_cls  = row.get("Asset Class", "").strip()

        if not ticker or ticker == "-" or not weight_str:
            continue
        # Only equity positions — skip cash, futures, fx hedges
        if asset_cls and "Equity" not in asset_cls:
            continue

        try:
            weight = float(weight_str)
            if weight > 0:
                weights[ticker] = weight
        except ValueError:
            continue

    return weights


def compute_and_cache_spx_impact(db: Session) -> dict:
    """
    Fetch constituent weights, batch-quote via Schwab, compute daily impact,
    and store top/bottom 10 in spx_impact_cache. Idempotent per ET calendar day.
    """
    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    existing = db.query(SpxImpactCache).first()
    if existing and existing.computed_date == today_et:
        logger.info("SPX impact: already computed today — skipping")
        return {"status": "skipped", "date": today_et}

    # ── 1. Constituent weights ───────────────────────────────────────────────
    try:
        weights = fetch_spx_weights()
        logger.info(f"SPX impact: loaded {len(weights)} constituent weights from IVV")
    except Exception as e:
        logger.error(f"SPX impact: failed to fetch IVV weights — {e}")
        return {"status": "error", "error": str(e)}

    if not weights:
        return {"status": "error", "error": "Empty weights dict from IVV CSV"}

    # ── 2. Batch quote all constituents via Schwab ───────────────────────────
    try:
        client = schwab_client_svc.get_schwab_client(db)
    except RuntimeError as e:
        logger.warning(f"SPX impact: Schwab client unavailable — {e}")
        return {"status": "error", "error": str(e)}

    tickers = list(weights.keys())
    logger.info(f"SPX impact: fetching quotes for {len(tickers)} constituents")

    try:
        resp = client.get_quotes(tickers)
        resp.raise_for_status()
        quotes = resp.json()
    except Exception as e:
        logger.error(f"SPX impact: Schwab batch quote failed — {e}")
        return {"status": "error", "error": str(e)}

    # ── 3. Compute per-ticker contribution ───────────────────────────────────
    impacts      = []
    spx_total    = 0.0
    priced_count = 0

    for ticker, weight_pct in weights.items():
        q_data = quotes.get(ticker, {})
        if not q_data:
            continue
        q          = q_data.get("quote", {})
        last_price = q.get("lastPrice") or q.get("mark")
        prev_close = q.get("closePrice")

        if not last_price or not prev_close or prev_close == 0:
            continue

        daily_return_pct = (last_price - prev_close) / prev_close * 100
        # Contribution to SPX daily return (percentage points)
        contribution = daily_return_pct * (weight_pct / 100)
        spx_total   += contribution
        priced_count += 1

        impacts.append({
            "ticker":           ticker,
            "daily_return_pct": round(daily_return_pct, 2),
            "weight_pct":       round(weight_pct, 2),
            "contribution":     round(contribution, 4),
        })

    if not impacts:
        return {"status": "error", "error": "No priced constituents returned from Schwab"}

    impacts.sort(key=lambda x: x["contribution"], reverse=True)
    contributors = impacts[:_TOP_N]
    detractors   = list(reversed(impacts[-_TOP_N:]))

    # ── 4. Persist ───────────────────────────────────────────────────────────
    row = existing or SpxImpactCache()
    row.computed_date     = today_et
    row.contributors_json = json.dumps(contributors)
    row.detractors_json   = json.dumps(detractors)
    row.spx_return_pct    = round(spx_total, 4)
    row.tickers_priced    = priced_count
    row.updated_at        = datetime.utcnow()

    if not existing:
        db.add(row)
    db.commit()

    logger.info(
        f"SPX impact: done — {priced_count} priced, "
        f"top: {contributors[0]['ticker']}, "
        f"worst: {detractors[0]['ticker']}, "
        f"est. SPX move: {spx_total:+.3f}%"
    )
    return {
        "status":         "ok",
        "date":           today_et,
        "tickers_priced": priced_count,
        "spx_return_pct": round(spx_total, 4),
    }
