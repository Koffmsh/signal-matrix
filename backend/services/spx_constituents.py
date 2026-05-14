"""
spx_constituents.py — SPX constituent weights + daily impact calculation.

Data source: iShares IVV holdings CSV (public, no auth required).
IVV tracks the S&P 500 index with constituent weights updated daily.

EOD flow (called from scheduler after calculate_signals):
  1. Fetch IVV holdings CSV → {ticker: weight_pct}
  2. Batch quote all ~503 constituents via Schwab
  3. Compute contribution = daily_return_pct × (weight_pct / 100)
  4. Store top 10 contributors + detractors + full weights_json in spx_impact_cache (label='eod')

Intraday flow (11am + 1pm scheduler jobs):
  1. Load weights from EOD row's weights_json — no IVV fetch needed
  2. Batch quote all ~503 constituents via Schwab (lastPrice, no AH strip)
  3. Compute + store top 10 contributors + detractors (label='11am' or '1pm')
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
_CHUNK = 200


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
        # DictReader fills short rows (e.g. footer text) with None — coerce before strip
        ticker     = (row.get("Ticker")      or "").strip().strip('"').upper()
        weight_str = (row.get("Weight (%)")  or "").strip()
        asset_cls  = (row.get("Asset Class") or "").strip()

        if not ticker or ticker == "-" or not weight_str:
            continue
        # Reject footer garbage — valid tickers are ≤ 6 chars with no spaces
        if len(ticker) > 6 or " " in ticker:
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


def _batch_schwab_quotes(client, tickers: list) -> dict:
    """Fetch quotes for all tickers in 200-ticker chunks. Returns {ticker: quote_data}."""
    quotes = {}
    for i in range(0, len(tickers), _CHUNK):
        chunk = tickers[i : i + _CHUNK]
        resp = client.get_quotes(chunk)
        resp.raise_for_status()
        quotes.update(resp.json())
    return quotes


def _compute_impacts(weights: dict, quotes: dict, strip_ah: bool = False) -> tuple:
    """
    Compute per-ticker contribution and contribution_norm.
    strip_ah=True for EOD (removes postMarketChange); False for intraday (lastPrice is live).
    Returns (impacts_list, spx_total, priced_count).
    """
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

        if strip_ah:
            post_market_change = q.get("postMarketChange") or 0
            current_price = last_price - post_market_change
        else:
            current_price = last_price

        daily_return_pct = (current_price - prev_close) / prev_close * 100
        contribution     = daily_return_pct * (weight_pct / 100)
        spx_total       += contribution
        priced_count    += 1

        impacts.append({
            "ticker":           ticker,
            "daily_return_pct": round(daily_return_pct, 2),
            "weight_pct":       round(weight_pct, 2),
            "contribution":     round(contribution, 4),
        })

    # Normalize: each stock's share of total gross index movement
    total_gross = sum(abs(x["contribution"]) for x in impacts)
    for x in impacts:
        x["contribution_norm"] = round(abs(x["contribution"]) / total_gross * 100, 2) if total_gross else 0

    return impacts, spx_total, priced_count


def compute_and_cache_spx_impact(db: Session) -> dict:
    """
    EOD run: fetch IVV weights + Schwab quotes, compute impact, persist as label='eod'.
    Also stores full weights_json for intraday runs to reuse.
    Idempotent per ET calendar day.
    """
    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    existing = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label == "eod"
    ).first()
    if existing and existing.computed_date == today_et:
        logger.info("SPX impact EOD: already computed today — skipping")
        return {"status": "skipped", "date": today_et}

    # ── 1. Constituent weights ───────────────────────────────────────────────
    try:
        weights = fetch_spx_weights()
        logger.info(f"SPX impact EOD: loaded {len(weights)} constituent weights from IVV")
    except Exception as e:
        logger.error(f"SPX impact EOD: failed to fetch IVV weights — {e}")
        return {"status": "error", "error": str(e)}

    if not weights:
        return {"status": "error", "error": "Empty weights dict from IVV CSV"}

    # ── 2. Batch quote all constituents via Schwab ───────────────────────────
    try:
        client = schwab_client_svc.get_schwab_client(db)
    except RuntimeError as e:
        logger.warning(f"SPX impact EOD: Schwab client unavailable — {e}")
        return {"status": "error", "error": str(e)}

    logger.info(f"SPX impact EOD: fetching quotes for {len(weights)} constituents")
    try:
        quotes = _batch_schwab_quotes(client, list(weights.keys()))
    except Exception as e:
        logger.error(f"SPX impact EOD: Schwab batch quote failed — {e}")
        return {"status": "error", "error": str(e)}

    # ── 3. Compute ───────────────────────────────────────────────────────────
    impacts, spx_total, priced_count = _compute_impacts(weights, quotes, strip_ah=True)

    if not impacts:
        return {"status": "error", "error": "No priced constituents returned from Schwab"}

    impacts.sort(key=lambda x: x["contribution"], reverse=True)
    contributors = impacts[:_TOP_N]
    detractors   = list(reversed(impacts[-_TOP_N:]))

    # ── 4. Persist ───────────────────────────────────────────────────────────
    row = existing or SpxImpactCache()
    row.snapshot_label    = "eod"
    row.computed_date     = today_et
    row.contributors_json = json.dumps(contributors)
    row.detractors_json   = json.dumps(detractors)
    row.spx_return_pct    = round(spx_total, 4)
    row.tickers_priced    = priced_count
    row.weights_json      = json.dumps(weights)
    row.updated_at        = datetime.utcnow()

    if not existing:
        db.add(row)
    db.commit()

    logger.info(
        f"SPX impact EOD: done — {priced_count} priced, "
        f"top: {contributors[0]['ticker']}, worst: {detractors[0]['ticker']}, "
        f"est. SPX move: {spx_total:+.3f}%"
    )
    return {
        "status":         "ok",
        "date":           today_et,
        "tickers_priced": priced_count,
        "spx_return_pct": round(spx_total, 4),
    }


def compute_and_cache_spx_impact_intraday(db: Session, label: str) -> dict:
    """
    Intraday run (label='11am' or '1pm'): reuse weights from EOD row, fetch live
    Schwab quotes, compute impact. No IVV fetch. No AH stripping (lastPrice is live).
    """
    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    # Load weights from most recent EOD row — doesn't have to be today's
    eod_row = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label == "eod"
    ).order_by(SpxImpactCache.computed_date.desc()).first()

    if not eod_row or not eod_row.weights_json:
        logger.warning(f"SPX impact {label}: no EOD weights available — skipping")
        return {"status": "error", "error": "No EOD weights available"}

    weights = json.loads(eod_row.weights_json)

    # ── Batch quote via Schwab ───────────────────────────────────────────────
    try:
        client = schwab_client_svc.get_schwab_client(db)
    except RuntimeError as e:
        logger.warning(f"SPX impact {label}: Schwab client unavailable — {e}")
        return {"status": "error", "error": str(e)}

    logger.info(f"SPX impact {label}: fetching live quotes for {len(weights)} constituents")
    try:
        quotes = _batch_schwab_quotes(client, list(weights.keys()))
    except Exception as e:
        logger.error(f"SPX impact {label}: Schwab batch quote failed — {e}")
        return {"status": "error", "error": str(e)}

    # ── Compute ──────────────────────────────────────────────────────────────
    impacts, spx_total, priced_count = _compute_impacts(weights, quotes, strip_ah=False)

    if not impacts:
        return {"status": "error", "error": "No priced constituents returned from Schwab"}

    impacts.sort(key=lambda x: x["contribution"], reverse=True)
    contributors = impacts[:_TOP_N]
    detractors   = list(reversed(impacts[-_TOP_N:]))

    # ── Upsert (overwrite if re-run same day) ────────────────────────────────
    existing = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label == label,
        SpxImpactCache.computed_date  == today_et,
    ).first()

    row = existing or SpxImpactCache()
    row.snapshot_label    = label
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
        f"SPX impact {label}: done — {priced_count} priced, "
        f"top: {contributors[0]['ticker']}, est. SPX move: {spx_total:+.3f}%"
    )
    return {
        "status":         "ok",
        "label":          label,
        "date":           today_et,
        "tickers_priced": priced_count,
        "spx_return_pct": round(spx_total, 4),
    }
