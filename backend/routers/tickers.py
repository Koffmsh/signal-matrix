from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.ticker import Ticker
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tickers", tags=["tickers"])

# ── Seed data — copied from src/data/tickers.js ───────────────────────────────
# This list is used once on first startup to populate the tickers table.
# After that, use the admin panel to manage tickers.

SEED_TICKERS = [
    # DOMESTIC EQUITIES — Index
    {"ticker": "SPX",   "description": "S&P 500 Index",                        "asset_class": "Domestic Equities",      "sector": "Index",                    "tier": 1, "parent_ticker": None, "active": True, "display_order": 1 },
    {"ticker": "NDX",   "description": "Nasdaq 100 Index",                     "asset_class": "Domestic Equities",      "sector": "Index",                    "tier": 1, "parent_ticker": None, "active": True, "display_order": 2 },
    {"ticker": "$DJI",  "description": "Dow Jones Industrial Avg",             "asset_class": "Domestic Equities",      "sector": "Index",                    "tier": 1, "parent_ticker": None, "active": True, "display_order": 3 },
    {"ticker": "VIX",   "description": "CBOE Volatility Index",                "asset_class": "Domestic Equities",      "sector": "Index",                    "tier": 1, "parent_ticker": None, "active": True, "display_order": 4 },
    # DOMESTIC EQUITIES — Broad Market
    {"ticker": "SPY",   "description": "SPDR S&P 500 ETF",                     "asset_class": "Domestic Equities",      "sector": "Broad Market",             "tier": 1, "parent_ticker": None, "active": True, "display_order": 5 },
    {"ticker": "QQQ",   "description": "Invesco Nasdaq 100 ETF",               "asset_class": "Domestic Equities",      "sector": "Broad Market",             "tier": 1, "parent_ticker": None, "active": True, "display_order": 6 },
    {"ticker": "IWM",   "description": "iShares Russell 2000 ETF",             "asset_class": "Domestic Equities",      "sector": "Broad Market",             "tier": 1, "parent_ticker": None, "active": True, "display_order": 7 },
    # DOMESTIC EQUITIES — Sector ETFs
    {"ticker": "XLK",   "description": "Technology Select Sector",             "asset_class": "Domestic Equities",      "sector": "Technology",               "tier": 1, "parent_ticker": None, "active": True, "display_order": 8 },
    {"ticker": "XLF",   "description": "Financial Select Sector",              "asset_class": "Domestic Equities",      "sector": "Financials",               "tier": 1, "parent_ticker": None, "active": True, "display_order": 9 },
    {"ticker": "XLE",   "description": "Energy Select Sector",                 "asset_class": "Domestic Equities",      "sector": "Energy",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 10},
    {"ticker": "XLV",   "description": "Health Care Select Sector",            "asset_class": "Domestic Equities",      "sector": "Health Care",              "tier": 1, "parent_ticker": None, "active": True, "display_order": 11},
    {"ticker": "XLI",   "description": "Industrials Select Sector",            "asset_class": "Domestic Equities",      "sector": "Industrials",              "tier": 1, "parent_ticker": None, "active": True, "display_order": 12},
    {"ticker": "XLY",   "description": "Consumer Discr. Select Sector",        "asset_class": "Domestic Equities",      "sector": "Consumer Discretionary",   "tier": 1, "parent_ticker": None, "active": True, "display_order": 13},
    {"ticker": "XLP",   "description": "Consumer Staples Select Sector",       "asset_class": "Domestic Equities",      "sector": "Consumer Staples",         "tier": 1, "parent_ticker": None, "active": True, "display_order": 14},
    {"ticker": "XLB",   "description": "Materials Select Sector",              "asset_class": "Domestic Equities",      "sector": "Materials",                "tier": 1, "parent_ticker": None, "active": True, "display_order": 15},
    {"ticker": "XLU",   "description": "Utilities Select Sector",              "asset_class": "Domestic Equities",      "sector": "Utilities",                "tier": 1, "parent_ticker": None, "active": True, "display_order": 16},
    {"ticker": "XLRE",  "description": "Real Estate Select Sector",            "asset_class": "Domestic Equities",      "sector": "Real Estate",              "tier": 1, "parent_ticker": None, "active": True, "display_order": 17},
    {"ticker": "XLC",   "description": "Communication Services Select Sector", "asset_class": "Domestic Equities",      "sector": "Communication Services",   "tier": 1, "parent_ticker": None, "active": True, "display_order": 18},
    # DOMESTIC EQUITIES — Individual Stocks
    {"ticker": "AAPL",  "description": "Apple Inc.",                           "asset_class": "Domestic Equities",      "sector": "Technology",               "tier": 1, "parent_ticker": None, "active": True, "display_order": 19},
    {"ticker": "MSFT",  "description": "Microsoft Corp.",                      "asset_class": "Domestic Equities",      "sector": "Technology",               "tier": 1, "parent_ticker": None, "active": True, "display_order": 20},
    {"ticker": "NVDA",  "description": "NVIDIA Corp.",                         "asset_class": "Domestic Equities",      "sector": "Technology",               "tier": 1, "parent_ticker": None, "active": True, "display_order": 21},
    {"ticker": "AVGO",  "description": "Broadcom Inc.",                        "asset_class": "Domestic Equities",      "sector": "Technology",               "tier": 1, "parent_ticker": None, "active": True, "display_order": 22},
    {"ticker": "GOOGL", "description": "Alphabet Inc.",                        "asset_class": "Domestic Equities",      "sector": "Communication Services",   "tier": 1, "parent_ticker": None, "active": True, "display_order": 23},
    {"ticker": "META",  "description": "Meta Platforms Inc.",                  "asset_class": "Domestic Equities",      "sector": "Communication Services",   "tier": 1, "parent_ticker": None, "active": True, "display_order": 24},
    {"ticker": "NFLX",  "description": "Netflix Inc.",                         "asset_class": "Domestic Equities",      "sector": "Communication Services",   "tier": 1, "parent_ticker": None, "active": True, "display_order": 25},
    {"ticker": "AMZN",  "description": "Amazon.com Inc.",                      "asset_class": "Domestic Equities",      "sector": "Consumer Discretionary",   "tier": 1, "parent_ticker": None, "active": True, "display_order": 26},
    {"ticker": "TSLA",  "description": "Tesla Inc.",                           "asset_class": "Domestic Equities",      "sector": "Consumer Discretionary",   "tier": 1, "parent_ticker": None, "active": True, "display_order": 27},
    # DOMESTIC EQUITIES — Factor ETFs
    {"ticker": "SMH",   "description": "VanEck Semiconductor ETF",             "asset_class": "Domestic Equities",      "sector": "Factor",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 28},
    {"ticker": "CIBR",  "description": "First Trust Cybersecurity ETF",        "asset_class": "Domestic Equities",      "sector": "Factor",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 29},
    {"ticker": "GRID",  "description": "First Trust Clean Edge Smart Grid",    "asset_class": "Domestic Equities",      "sector": "Factor",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 30},
    {"ticker": "QTUM",  "description": "Defiance Quantum ETF",                 "asset_class": "Domestic Equities",      "sector": "Factor",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 31},
    {"ticker": "ROBO",  "description": "ROBO Global Robotics & Auto ETF",      "asset_class": "Domestic Equities",      "sector": "Factor",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 32},
    {"ticker": "SATS",  "description": "ETF Series Space & Defense",           "asset_class": "Domestic Equities",      "sector": "Factor",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 33},
    # DOMESTIC FIXED INCOME
    {"ticker": "TLT",   "description": "iShares 20+ Year Treasury Bond ETF",   "asset_class": "Domestic Fixed Income",  "sector": "Treasury",                 "tier": 1, "parent_ticker": None, "active": True, "display_order": 34},
    # DIGITAL ASSETS
    {"ticker": "IBIT",  "description": "iShares Bitcoin Trust ETF",            "asset_class": "Digital Assets",         "sector": "Cryptocurrency",           "tier": 1, "parent_ticker": None, "active": True, "display_order": 35},
    # FOREIGN EXCHANGE
    {"ticker": "GLD",   "description": "SPDR Gold Shares",                     "asset_class": "Foreign Exchange",       "sector": "Gold",                     "tier": 1, "parent_ticker": None, "active": True, "display_order": 36},
    {"ticker": "USD",   "description": "US Dollar Index",                      "asset_class": "Foreign Exchange",       "sector": "Currency",                 "tier": 1, "parent_ticker": None, "active": True, "display_order": 37},
    {"ticker": "JPY",   "description": "Japanese Yen / USD",                   "asset_class": "Foreign Exchange",       "sector": "Currency",                 "tier": 1, "parent_ticker": None, "active": True, "display_order": 38},
    # INTERNATIONAL EQUITIES
    {"ticker": "KWEB",  "description": "KraneShares CSI China Internet ETF",   "asset_class": "International Equities", "sector": "China",                    "tier": 1, "parent_ticker": None, "active": True, "display_order": 39},
    {"ticker": "EWJ",   "description": "iShares MSCI Japan ETF",               "asset_class": "International Equities", "sector": "Japan",                    "tier": 1, "parent_ticker": None, "active": True, "display_order": 40},
    {"ticker": "EWW",   "description": "iShares MSCI Mexico ETF",              "asset_class": "International Equities", "sector": "Mexico",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 41},
    {"ticker": "TUR",   "description": "iShares MSCI Turkey ETF",              "asset_class": "International Equities", "sector": "Turkey",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 42},
    {"ticker": "UAE",   "description": "iShares MSCI UAE ETF",                 "asset_class": "International Equities", "sector": "UAE",                      "tier": 1, "parent_ticker": None, "active": True, "display_order": 43},
    # COMMODITIES
    {"ticker": "USO",   "description": "United States Oil Fund",               "asset_class": "Commodities",            "sector": "Energy",                   "tier": 1, "parent_ticker": None, "active": True, "display_order": 44},
    {"ticker": "SLV",   "description": "iShares Silver Trust",                 "asset_class": "Commodities",            "sector": "Precious Metals",          "tier": 1, "parent_ticker": None, "active": True, "display_order": 45},
    {"ticker": "PALL",  "description": "Aberdeen Physical Palladium",          "asset_class": "Commodities",            "sector": "Precious Metals",          "tier": 1, "parent_ticker": None, "active": True, "display_order": 46},
    {"ticker": "CANE",  "description": "Teucrium Sugar Fund",                  "asset_class": "Commodities",            "sector": "Agricultural",             "tier": 1, "parent_ticker": None, "active": True, "display_order": 47},
    {"ticker": "WOOD",  "description": "iShares Global Timber & Forestry ETF", "asset_class": "Commodities",            "sector": "Materials",                "tier": 1, "parent_ticker": None, "active": True, "display_order": 48},
    # TIER 2 — seed data
    {"ticker": "XOP",   "description": "SPDR S&P Oil & Gas Explor & Prod ETF", "asset_class": "Commodities",            "sector": "Energy",                   "tier": 2, "parent_ticker": "USO", "active": True, "display_order": 1 },
    {"ticker": "OIH",   "description": "VanEck Oil Services ETF",              "asset_class": "Commodities",            "sector": "Energy",                   "tier": 2, "parent_ticker": "USO", "active": True, "display_order": 2 },
    {"ticker": "SOXX",  "description": "iShares Semiconductor ETF",            "asset_class": "Domestic Equities",      "sector": "Technology",               "tier": 2, "parent_ticker": "XLK", "active": True, "display_order": 1 },
    {"ticker": "SGOL",  "description": "Aberdeen Physical Gold Shares ETF",    "asset_class": "Foreign Exchange",       "sector": "Gold",                     "tier": 2, "parent_ticker": "GLD", "active": True, "display_order": 1 },
]

# Note: AMZN appears as both Tier 1 and Tier 2 (child of XLY) in tickers.js.
# The DB enforces UNIQUE(ticker), so we only seed the Tier 1 record.
# The Tier 2 AMZN/XLY relationship can be added via admin panel if needed.


def seed_tickers_if_empty(db: Session) -> None:
    count = db.query(Ticker).count()
    if count > 0:
        logger.info(f"Ticker DB already populated ({count} rows) — skipping seed")
        return

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for t in SEED_TICKERS:
        db.add(Ticker(
            ticker        = t["ticker"],
            description   = t["description"],
            asset_class   = t["asset_class"],
            sector        = t["sector"],
            tier          = t["tier"],
            parent_ticker = t["parent_ticker"],
            active        = t["active"],
            display_order = t["display_order"],
            created_at    = now,
            updated_at    = now,
        ))
    db.commit()
    logger.info(f"Seeded {len(SEED_TICKERS)} tickers")


def _row_to_dict(row: Ticker) -> dict:
    return {
        "id":           row.id,
        "ticker":       row.ticker,
        "description":  row.description,
        "asset_class":  row.asset_class,
        "sector":       row.sector,
        "tier":         row.tier,
        "parent_ticker": row.parent_ticker,
        "active":       row.active,
        "display_order": row.display_order,
        "created_at":   row.created_at,
        "updated_at":   row.updated_at,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def get_tickers(
    tier:   Optional[int]  = None,
    active: Optional[bool] = None,   # None = all, True = active only, False = inactive only
    db:     Session        = Depends(get_db),
):
    q = db.query(Ticker)
    if tier is not None:
        q = q.filter(Ticker.tier == tier)
    if active is not None:
        q = q.filter(Ticker.active == active)
    rows = q.order_by(Ticker.tier, Ticker.display_order).all()
    return [_row_to_dict(r) for r in rows]


@router.post("")
def create_ticker(body: dict, db: Session = Depends(get_db)):
    symbol = (body.get("ticker") or "").upper().strip()
    if not symbol:
        raise HTTPException(status_code=422, detail="ticker is required")

    existing = db.query(Ticker).filter(Ticker.ticker == symbol).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"{symbol} already exists")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    row = Ticker(
        ticker        = symbol,
        description   = body.get("description"),
        asset_class   = body.get("asset_class"),
        sector        = body.get("sector"),
        tier          = body.get("tier", 1),
        parent_ticker = body.get("parent_ticker"),
        active        = body.get("active", True),
        display_order = body.get("display_order", 999),
        created_at    = now,
        updated_at    = now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(f"Created ticker: {symbol}")
    return _row_to_dict(row)


def _map_asset_class(quote_type: str, sector: str, category: str, symbol: str):
    qt  = (quote_type or "").upper()
    sec = (sector   or "").lower()
    cat = (category or "").lower()

    if qt == "ETF":
        # Gold symbols — Foreign Exchange before generic commodity check
        if symbol.upper() in ("GLD", "IAU", "SGOL", "GLDM", "BAR"):
            return "Foreign Exchange"
        if "gold" in cat:
            return "Foreign Exchange"
        # Currency
        if any(x in cat for x in ["currency", "forex", "pound", "euro", "yen"]):
            return "Foreign Exchange"
        # Commodities — check before International to avoid false "commodities focused" → international
        if any(x in cat for x in ["commodit", "energy", "metal", "agriculture", "oil", "silver", "copper", "natural resource"]):
            return "Commodities"
        # Fixed Income
        if any(x in cat for x in ["bond", "treasury", "fixed income", "corporate bond", "credit", "inflation-protected", "government", "muni", "high yield"]):
            return "Domestic Fixed Income"
        # International — includes "region" categories (e.g. "China Region", "Miscellaneous Region")
        if any(x in cat for x in ["international", "foreign", "emerging", "world", "global", "europe", "asia", "pacific", "latin", "region", "china", "japan", "india"]):
            return "International Equities"
        # Digital Assets
        if any(x in cat for x in ["bitcoin", "crypto", "digital asset", "blockchain", "digital currency"]):
            return "Digital Assets"
        return "Domestic Equities"  # default ETF

    if qt == "EQUITY":
        if any(x in sec for x in ["international", "foreign"]):
            return "International Equities"
        return "Domestic Equities"

    if qt in ("CRYPTOCURRENCY", "CRYPTO"):
        return "Digital Assets"

    if qt == "CURRENCY":
        return "Foreign Exchange"

    return None  # futures, unknown — user fills manually


@router.get("/lookup/{symbol}")
def lookup_ticker(symbol: str, db: Session = Depends(get_db)):
    """
    Task 4.7 — On-demand yfinance metadata lookup for a ticker symbol.
    Returns suggestions only — never writes to DB. Graceful on all errors.
    """
    import yfinance as yf

    symbol = symbol.upper().strip()

    already_exists = db.query(Ticker).filter(Ticker.ticker == symbol).first() is not None

    try:
        info = yf.Ticker(symbol).info

        # yfinance returns minimal/empty dict for invalid symbols
        if not info or (info.get("regularMarketPrice") is None and info.get("navPrice") is None and info.get("previousClose") is None):
            return {
                "symbol":         symbol,
                "found":          False,
                "suggestions":    None,
                "already_exists": already_exists,
                "notes":          "Symbol not found on Yahoo Finance",
            }

        description  = info.get("longName") or info.get("shortName") or None
        sector       = info.get("sector") or info.get("category") or None
        asset_class  = _map_asset_class(
            quote_type = info.get("quoteType"),
            sector     = info.get("sector"),
            category   = info.get("category"),
            symbol     = symbol,
        )

        notes = None
        if already_exists:
            notes = "Ticker already exists in Signal Matrix"
        elif description is None or asset_class is None or sector is None:
            notes = "Some fields could not be determined — please review"

        return {
            "symbol": symbol,
            "found":  True,
            "suggestions": {
                "description": description,
                "asset_class": asset_class,
                "sector":      sector,
            },
            "already_exists": already_exists,
            "notes":          notes,
        }

    except Exception as e:
        logger.warning(f"Lookup failed for {symbol}: {e}")
        return {
            "symbol":         symbol,
            "found":          False,
            "suggestions":    None,
            "already_exists": already_exists,
            "notes":          "Lookup failed — please enter details manually",
        }


@router.put("/{symbol}")
def update_ticker(symbol: str, body: dict, db: Session = Depends(get_db)):
    symbol = symbol.upper()
    row = db.query(Ticker).filter(Ticker.ticker == symbol).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{symbol} not found")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    if "description"   in body: row.description   = body["description"]
    if "asset_class"   in body: row.asset_class   = body["asset_class"]
    if "sector"        in body: row.sector         = body["sector"]
    if "tier"          in body: row.tier           = body["tier"]
    if "parent_ticker" in body: row.parent_ticker  = body["parent_ticker"]
    if "active"        in body: row.active         = body["active"]
    if "display_order" in body: row.display_order  = body["display_order"]
    row.updated_at = now

    db.commit()
    db.refresh(row)
    logger.info(f"Updated ticker: {symbol}")
    return _row_to_dict(row)


@router.delete("/{symbol}")
def deactivate_ticker(symbol: str, db: Session = Depends(get_db)):
    symbol = symbol.upper()
    row = db.query(Ticker).filter(Ticker.ticker == symbol).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{symbol} not found")

    row.active     = False
    row.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    db.refresh(row)
    logger.info(f"Deactivated ticker: {symbol}")
    return _row_to_dict(row)
