import json
import bisect
from datetime import datetime, date
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, load_only
from database import SessionLocal
from models.price_cache import PriceCache

router = APIRouter()
_ET = ZoneInfo("America/New_York")

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


@router.get("/api/sector-performance")
def get_sector_performance(db: Session = Depends(get_db)):
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

        current  = prices[-1]
        prev_1d  = prices[-2] if len(prices) >= 2 else None
        prev_ytd = _find_price_before(dates, prices, ytd_start)
        prev_qtd = _find_price_before(dates, prices, qtd_start)
        prev_mtd = _find_price_before(dates, prices, mtd_start)

        computed[ticker] = {
            "ticker":      ticker,
            "description": desc_map[ticker],
            "close":       row.close,   # price_cache.close is most-recent EOD
            "chg_1d":      _pct(prev_1d,  current),
            "chg_mtd":     _pct(prev_mtd, current),
            "chg_qtd":     _pct(prev_qtd, current),
            "chg_ytd":     _pct(prev_ytd, current),
        }

    # ── SPX baseline for relative table ──────────────────────────────────────
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

    # Period labels for the header (e.g. "May 2026", "Q2 2026")
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
