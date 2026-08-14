import json
import bisect
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, load_only
from database import SessionLocal
from models.price_cache import PriceCache

router = APIRouter()
_ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)

# Ordered display list — SPX pinned last in the absolute table
SECTOR_TICKERS = [
    ("XLY",  "Consumer Discretionary"),
    ("XLF",  "Financial Select Sector"),
    ("XLV",  "Health Care Select Sector"),
    ("XLK",  "Technology Select Sector"),
    ("XLP",  "Consumer Staples Select Sector"),
    ("XLI",  "Industrial Select Sector"),
    ("XLB",  "Materials Select Sector"),
    ("XLE",  "Energy Select Sector"),
    ("XLU",  "Utilities Select Sector"),
    ("XLRE", "Real Estate Select Sector"),
    ("XLC",  "Communications Services Sector"),
    ("SPX",  "S&P 500"),
]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _find_price_before(dates: list, prices: list, start_date: str):
    """
    Return the last close price strictly BEFORE start_date.
    e.g. for MTD start "2026-05-01", returns Apr 30 close.
    """
    idx = bisect.bisect_left(dates, start_date)
    if idx == 0:
        return None
    return prices[idx - 1]


def _pct(start, end):
    if start is None or end is None or start == 0:
        return None
    return (end - start) / start * 100


def _quarter_start(d: date) -> str:
    q_month = ((d.month - 1) // 3) * 3 + 1   # 1, 4, 7, or 10
    return date(d.year, q_month, 1).strftime("%Y-%m-%d")


def _year_start(d: date) -> str:
    return date(d.year, 1, 1).strftime("%Y-%m-%d")


def _month_start(d: date) -> str:
    return date(d.year, d.month, 1).strftime("%Y-%m-%d")


def _compute_sector_perf(db: Session, live_prices: dict | None = None):
    """Core computation shared by EOD and LIVE modes.
    live_prices: optional {ticker: price} override for current close.
    """
    all_tickers = [t for t, _ in SECTOR_TICKERS]
    desc_map    = {t: d for t, d in SECTOR_TICKERS}

    rows = (
        db.query(PriceCache)
        .filter(PriceCache.ticker.in_(all_tickers))
        .options(
            load_only(
                PriceCache.ticker,
                PriceCache.close,
                PriceCache.history_json,
                PriceCache.history_dates_json,
            )
        )
        .all()
    )

    cache = {r.ticker: r for r in rows}

    today_et  = datetime.now(_ET).date()
    ytd_start = _year_start(today_et)
    qtd_start = _quarter_start(today_et)
    mtd_start = _month_start(today_et)

    computed: dict[str, dict | None] = {}
    for ticker in all_tickers:
        row = cache.get(ticker)
        if not row or not row.history_json or not row.history_dates_json:
            computed[ticker] = None
            continue

        prices = json.loads(row.history_json)
        dates  = json.loads(row.history_dates_json)

        if not prices or not dates or len(prices) != len(dates):
            computed[ticker] = None
            continue

        current = live_prices.get(ticker) if live_prices and ticker in live_prices else prices[-1]
        prev_1d  = prices[-2] if len(prices) >= 2 else None
        prev_ytd = _find_price_before(dates, prices, ytd_start)
        prev_qtd = _find_price_before(dates, prices, qtd_start)
        prev_mtd = _find_price_before(dates, prices, mtd_start)

        computed[ticker] = {
            "ticker":      ticker,
            "description": desc_map[ticker],
            "close":       round(current, 2) if current else None,
            "chg_1d":      _pct(prev_1d,  current),
            "chg_mtd":     _pct(prev_mtd, current),
            "chg_qtd":     _pct(prev_qtd, current),
            "chg_ytd":     _pct(prev_ytd, current),
        }

    spx = computed.get("SPX") or {}
    spx_1d  = spx.get("chg_1d")
    spx_mtd = spx.get("chg_mtd")
    spx_qtd = spx.get("chg_qtd")
    spx_ytd = spx.get("chg_ytd")

    def rel(val, base):
        return None if (val is None or base is None) else val - base

    absolute = []
    relative = []

    for ticker, desc in SECTOR_TICKERS:
        r = computed.get(ticker) or {
            "ticker": ticker, "description": desc, "close": None,
            "chg_1d": None, "chg_mtd": None, "chg_qtd": None, "chg_ytd": None,
        }
        absolute.append(r)

        if ticker != "SPX":
            relative.append({
                "ticker":      ticker,
                "description": desc,
                "close":       r["close"],
                "chg_1d":      rel(r["chg_1d"],  spx_1d),
                "chg_mtd":     rel(r["chg_mtd"], spx_mtd),
                "chg_qtd":     rel(r["chg_qtd"], spx_qtd),
                "chg_ytd":     rel(r["chg_ytd"], spx_ytd),
            })

    month_label = today_et.strftime("%b %Y")
    quarter     = (today_et.month - 1) // 3 + 1
    qtd_label   = f"Q{quarter} {today_et.year}"
    ytd_label   = str(today_et.year)

    return {
        "absolute": absolute,
        "relative": relative,
        "labels": {
            "mtd": month_label,
            "qtd": qtd_label,
            "ytd": ytd_label,
        },
        "as_of": today_et.strftime("%B %d, %Y"),
    }


@router.get("/api/sector-performance")
def get_sector_performance(live: bool = Query(False), db: Session = Depends(get_db)):
    if not live:
        result = _compute_sector_perf(db)
        result["mode"] = "eod"
        result["refreshed_at"] = None
        return result

    # Live mode — fetch fresh Schwab quotes for sector tickers
    sector_syms = [t for t, _ in SECTOR_TICKERS]
    live_prices = {}
    try:
        from services.schwab_client import get_schwab_client
        from services.schwab_market_data import get_schwab_symbol
        client = get_schwab_client(db)
        schwab_syms = [get_schwab_symbol(t) for t in sector_syms]
        resp = client.get_quotes(schwab_syms)
        resp.raise_for_status()
        quotes = resp.json()
        for app_ticker in sector_syms:
            schwab_sym = get_schwab_symbol(app_ticker)
            q = quotes.get(schwab_sym, {}).get("quote", {})
            price = q.get("lastPrice")
            if price:
                live_prices[app_ticker] = price
    except Exception as e:
        logger.warning(f"Sector live quotes failed: {e} — falling back to cached")

    # SPX is in SCHWAB_UNSUPPORTED — batch quotes silently drops indices.
    # Fall back to Yahoo delayed quote for SPX if Schwab didn't return it.
    if "SPX" not in live_prices:
        try:
            import yfinance as yf
            tk = yf.Ticker("^GSPC")
            info = tk.fast_info
            price = getattr(info, "last_price", None)
            if price:
                live_prices["SPX"] = price
        except Exception as e:
            logger.warning(f"Yahoo SPX fallback failed: {e}")

    now_et = datetime.now(_ET)
    result = _compute_sector_perf(db, live_prices if live_prices else None)
    result["mode"] = "live"
    result["refreshed_at"] = now_et.strftime("%I:%M %p ET").lstrip("0")
    return result
