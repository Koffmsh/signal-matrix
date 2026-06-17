"""
spx_constituents.py — SPX constituent weights + daily impact calculation.

Data source: SSGA SPY daily holdings XLSX (public, no auth required).
SPY tracks the S&P 500 index with constituent weights updated daily.

EOD flow (called from scheduler after calculate_signals):
  1. Fetch SPY holdings XLSX → {ticker: weight_pct}
  2. Batch quote all ~503 constituents via Schwab
  3. Compute contribution = daily_return_pct × (weight_pct / 100)
  4. Store top 10 contributors + detractors + full weights_json in spx_impact_cache (label='eod')

Intraday flow (11am + 1pm scheduler jobs):
  1. Load weights from EOD row's weights_json — no SPY fetch needed
  2. Batch quote all ~503 constituents via Schwab (lastPrice, no AH strip)
  3. Compute + store top 10 contributors + detractors (label='11am' or '1pm')
"""

import io
import json
import logging
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

import services.schwab_client as schwab_client_svc
from models.spx_impact_cache import SpxImpactCache
from models.price_cache import PriceCache

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# SSGA SPY (S&P 500 ETF) daily holdings XLSX — public download, no auth required
_SPY_HOLDINGS_URL = (
    "https://www.ssga.com/library-content/products/fund-data/etfs/us/"
    "holdings-daily-us-en-spy.xlsx"
)

_TOP_N = 10
_CHUNK = 200
_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def parse_spy_xlsx(content: bytes) -> tuple[dict, str]:
    """
    Parse SSGA SPY daily holdings XLSX → ({ticker: weight_pct}, as_of_date).
    Parses raw XLSX ZIP without requiring openpyxl.
    Row 5 = header (Name/Ticker/Weight/Sector…); rows 6+ = data.
    as_of_date is extracted from shared strings ("As of DD-Mon-YYYY") → "YYYY-MM-DD".
    """
    zf = zipfile.ZipFile(io.BytesIO(content))

    # Shared string table
    ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for si in ss_root.findall(f"{{{_XLSX_NS}}}si"):
        t = si.find(f".//{{{_XLSX_NS}}}t")
        strings.append(t.text if t is not None else "")

    # Extract "As of DD-Mon-YYYY" → "YYYY-MM-DD"
    as_of_date = None
    for s in strings:
        if s and s.startswith("As of "):
            try:
                as_of_date = datetime.strptime(s[6:], "%d-%b-%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
            break

    sheet_root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
    ticker_col = weight_col = None
    weights = {}

    for row_el in sheet_root.iter(f"{{{_XLSX_NS}}}row"):
        r = int(row_el.get("r", 0))
        if r < 5:
            continue

        cells = {}
        for c in row_el:
            col_ref = c.get("r", "")
            col_letter = "".join(ch for ch in col_ref if ch.isalpha())
            v_el = c.find(f"{{{_XLSX_NS}}}v")
            if v_el is None:
                continue
            if c.get("t") == "s":
                cells[col_letter] = strings[int(v_el.text)]
            else:
                try:
                    cells[col_letter] = float(v_el.text)
                except (ValueError, TypeError):
                    cells[col_letter] = v_el.text

        if r == 5:  # header row — locate Ticker and Weight columns
            for col, val in cells.items():
                if val == "Ticker":
                    ticker_col = col
                elif val == "Weight":
                    weight_col = col
            continue

        if not ticker_col or not weight_col:
            continue

        ticker = str(cells.get(ticker_col, "")).strip().upper()
        weight = cells.get(weight_col)
        if not ticker or ticker == "-" or weight is None:
            continue
        if len(ticker) > 6 or " " in ticker:
            continue
        try:
            w = float(weight)
            if w > 0:
                weights[ticker] = w
        except (ValueError, TypeError):
            continue

    return weights, as_of_date or datetime.now(_ET).strftime("%Y-%m-%d")


def fetch_spx_weights() -> tuple[dict, str]:
    """
    Download SSGA SPY holdings XLSX and return ({ticker: weight_pct}, as_of_date).
    Raises on network or parse failure.
    """
    resp = httpx.get(
        _SPY_HOLDINGS_URL,
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    if resp.content[:2] != b"PK":
        raise ValueError("SPY holdings response is not a valid XLSX file — URL may have changed")
    return parse_spy_xlsx(resp.content)


def _get_spx_actual_return(db: Session, is_eod: bool) -> float | None:
    """
    Actual SPX daily % change from price_cache.
    EOD: history_json[-1] (today's close) vs history_json[-2] (yesterday's close).
    Intraday: price_cache.close (live intraday) vs history_json[-1] (yesterday's EOD close).
    """
    spx = db.query(PriceCache).filter(PriceCache.ticker == "SPX").first()
    if not spx or not spx.history_json:
        return None
    closes = json.loads(spx.history_json)
    if is_eod:
        if len(closes) < 2 or not closes[-2]:
            return None
        return round((closes[-1] - closes[-2]) / closes[-2] * 100, 4)
    else:
        if not spx.close or not closes or not closes[-1]:
            return None
        return round((spx.close - closes[-1]) / closes[-1] * 100, 4)


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
    weights_date = today_et
    weights_stale = False
    try:
        weights, weights_date = fetch_spx_weights()
        if not weights:
            raise ValueError("Empty weights dict from SPY XLSX")
        logger.info(f"SPX impact EOD: loaded {len(weights)} constituent weights from SPY (as of {weights_date})")
    except Exception as e:
        logger.warning(f"SPX impact EOD: IVV fetch failed ({e}) — attempting fallback to last known weights")
        # Fall back to the most recent EOD row that has weights_json
        fallback = db.query(SpxImpactCache).filter(
            SpxImpactCache.snapshot_label == "eod",
            SpxImpactCache.weights_json.isnot(None),
        ).order_by(SpxImpactCache.computed_date.desc()).first()
        if not fallback or not fallback.weights_json:
            logger.error("SPX impact EOD: no fallback weights available — aborting")
            return {"status": "error", "error": str(e)}
        weights = json.loads(fallback.weights_json)
        weights_date = fallback.weights_date or fallback.computed_date
        weights_stale = True
        logger.info(f"SPX impact EOD: using fallback weights from {weights_date} ({len(weights)} tickers)")

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
    spx_actual = _get_spx_actual_return(db, is_eod=True)

    row = existing or SpxImpactCache()
    row.snapshot_label    = "eod"
    row.computed_date     = today_et
    row.contributors_json = json.dumps(contributors)
    row.detractors_json   = json.dumps(detractors)
    row.spx_return_pct    = spx_actual
    row.tickers_priced    = priced_count
    row.weights_date      = weights_date
    if not weights_stale:
        row.weights_json  = json.dumps(weights)  # only overwrite on fresh fetch
    row.updated_at        = datetime.utcnow()

    if not existing:
        db.add(row)
    db.commit()

    logger.info(
        f"SPX impact EOD: done — {priced_count} priced, "
        f"top: {contributors[0]['ticker']}, worst: {detractors[0]['ticker']}, "
        f"SPX actual: {spx_actual:+.3f}% (est: {spx_total:+.3f}%), "
        f"weights: {'stale (' + weights_date + ')' if weights_stale else 'fresh'}"
    )
    return {
        "status":         "ok",
        "date":           today_et,
        "tickers_priced": priced_count,
        "spx_return_pct": spx_actual,
        "weights_date":   weights_date,
        "weights_stale":  weights_stale,
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

    spx_actual = _get_spx_actual_return(db, is_eod=False)

    row = existing or SpxImpactCache()
    row.snapshot_label    = label
    row.computed_date     = today_et
    row.contributors_json = json.dumps(contributors)
    row.detractors_json   = json.dumps(detractors)
    row.spx_return_pct    = spx_actual
    row.tickers_priced    = priced_count
    row.updated_at        = datetime.utcnow()

    if not existing:
        db.add(row)
    db.commit()

    logger.info(
        f"SPX impact {label}: done — {priced_count} priced, "
        f"top: {contributors[0]['ticker']}, SPX actual: {spx_actual:+.3f}%"
    )
    return {
        "status":         "ok",
        "label":          label,
        "date":           today_et,
        "tickers_priced": priced_count,
        "spx_return_pct": round(spx_total, 4),
    }
