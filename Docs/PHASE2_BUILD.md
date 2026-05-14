# Signal Matrix — Phase 2 Build Instructions
# For Neo (Claude Code) — Execute in order, confirm each step before proceeding

## Overview
Add a Python FastAPI backend to the existing React app.
Backend fetches real market data from Yahoo Finance.
React merges real data over mock signal data.
All contained in Docker Compose.

Project path: C:\Projects\signal-matrix

---

## STEP 1 — Create backend folder and all files

Create the folder `C:\Projects\signal-matrix\backend\` and the following files inside it.

---

### FILE: backend/requirements.txt

```
fastapi==0.109.0
uvicorn==0.27.0
yfinance==0.2.36
sqlalchemy==2.0.25
pandas==2.2.0
python-dotenv==1.0.0
httpx==0.26.0
```

---

### FILE: backend/Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

---

### FILE: backend/database.py

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./signal_matrix.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

### FILE: backend/models/__init__.py

```python
from .price_cache import PriceCache
```

---

### FILE: backend/models/price_cache.py

```python
from sqlalchemy import Column, String, Float, Integer, DateTime, Text
from sqlalchemy.sql import func
from database import Base

class PriceCache(Base):
    __tablename__ = "price_cache"

    id           = Column(Integer, primary_key=True, index=True)
    ticker       = Column(String, index=True)
    yahoo_symbol = Column(String)
    close        = Column(Float)
    volume       = Column(Float)
    ma20         = Column(Float)
    ma50         = Column(Float)
    ma100        = Column(Float)
    rel_iv       = Column(Integer)   # realized vol percentile 0-100
    spark_json   = Column(Text)      # JSON array of 60 closing prices
    updated_at   = Column(DateTime(timezone=True), server_default=func.now())
    cache_date   = Column(String)    # YYYY-MM-DD — cache invalidation key
```

---

### FILE: backend/services/__init__.py

```python
```

---

### FILE: backend/services/yahoo_finance.py

```python
import yfinance as yf
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Symbol mapping — dashboard ticker -> Yahoo Finance symbol
YAHOO_SYMBOL_MAP = {
    "SPX":  "^GSPC",
    "NDX":  "^NDX",
    "$DJI": "^DJI",
    "VIX":  "^VIX",
    "USD":  "DX-Y.NYB",
    "JPY":  "JPY=X",
}

def get_yahoo_symbol(ticker: str) -> str:
    return YAHOO_SYMBOL_MAP.get(ticker, ticker)


def fetch_ticker_data(ticker: str) -> dict | None:
    """
    Fetch 14 months of history for a ticker (ensures 252 trading days).
    Returns dict with close, volume, ma20/50/100, rel_iv, spark_prices.
    Returns None if fetch fails.
    """
    yahoo_symbol = get_yahoo_symbol(ticker)

    try:
        yf_ticker = yf.Ticker(yahoo_symbol)
        hist = yf_ticker.history(period="14mo")

        if hist.empty or len(hist) < 20:
            logger.warning(f"Insufficient data for {ticker} ({yahoo_symbol})")
            return None

        closes  = hist["Close"].dropna()
        volumes = hist["Volume"].dropna()

        # Latest values
        close  = round(float(closes.iloc[-1]), 2)
        volume = int(volumes.iloc[-1]) if not volumes.empty else 0

        # Moving averages — computed from close history
        ma20  = round(float(closes.tail(20).mean()),  2) if len(closes) >= 20  else None
        ma50  = round(float(closes.tail(50).mean()),  2) if len(closes) >= 50  else None
        ma100 = round(float(closes.tail(100).mean()), 2) if len(closes) >= 100 else None

        # Realized volatility percentile (proxy for Rel IV until Schwab Phase 5)
        rel_iv = compute_realized_vol_percentile(closes)

        # Sparkline — last 60 closes, last point anchored to current close
        spark_window = closes.tail(60).tolist()
        spark_prices = [round(p, 2) for p in spark_window]
        if spark_prices:
            spark_prices[-1] = close  # Ensure last point = exact close

        updated = datetime.now().strftime("%m/%d/%y %H:%M")

        return {
            "ticker":        ticker,
            "yahoo_symbol":  yahoo_symbol,
            "close":         close,
            "volume":        volume,
            "ma20":          ma20,
            "ma50":          ma50,
            "ma100":         ma100,
            "rel_iv":        rel_iv,
            "spark_prices":  spark_prices,
            "updated":       updated,
        }

    except Exception as e:
        logger.error(f"Failed to fetch {ticker} ({yahoo_symbol}): {e}")
        return None


def compute_realized_vol_percentile(closes: pd.Series) -> int:
    """
    Realized volatility percentile (0-100) as Rel IV proxy.
    Method: 21-day rolling annualized realized vol, percentile rank
    within its own 252-day history.
    Replaced by Schwab IV Percentile in Phase 5.
    """
    try:
        if len(closes) < 42:
            return 50  # Insufficient data — default to midpoint

        log_returns  = closes.pct_change().dropna()
        rolling_vol  = log_returns.rolling(21).std() * (252 ** 0.5)
        rolling_vol  = rolling_vol.dropna()

        if len(rolling_vol) < 2:
            return 50

        current_vol  = rolling_vol.iloc[-1]
        hist_vol     = rolling_vol.tail(252)
        percentile   = int((hist_vol < current_vol).sum() / len(hist_vol) * 100)

        return max(0, min(100, percentile))

    except Exception:
        return 50  # Safe default
```

---

### FILE: backend/routers/__init__.py

```python
```

---

### FILE: backend/routers/market_data.py

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.price_cache import PriceCache
from services.yahoo_finance import fetch_ticker_data
from datetime import date
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market-data", tags=["market-data"])

# Full Tier 1 ticker list — must match tickers.js
TIER1_TICKERS = [
    "SPX", "NDX", "$DJI", "VIX",
    "SPY", "QQQ", "IWM",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE", "XLC",
    "AAPL", "MSFT", "NVDA", "AVGO", "GOOGL", "META", "NFLX", "AMZN", "TSLA",
    "SMH", "CIBR", "GRID", "QTUM", "ROBO", "SATS",
    "TLT", "IBIT", "GLD", "USD", "JPY",
    "KWEB", "EWJ", "EWW", "TUR", "UAE",
    "USO", "SLV", "PALL", "CANE", "WOOD",
]


def serialize_cache_row(row: PriceCache) -> dict:
    return {
        "ticker":       row.ticker,
        "close":        row.close,
        "volume":       row.volume,
        "ma20":         row.ma20,
        "ma50":         row.ma50,
        "ma100":        row.ma100,
        "rel_iv":       row.rel_iv,
        "spark_prices": json.loads(row.spark_json),
        "updated":      str(row.updated_at),
    }


def get_or_fetch(ticker: str, today: str, db: Session) -> dict | None:
    """Return cached data if fresh for today, otherwise fetch and cache."""
    cached = db.query(PriceCache).filter(
        PriceCache.ticker     == ticker,
        PriceCache.cache_date == today
    ).first()

    if cached:
        logger.info(f"Cache hit: {ticker}")
        return serialize_cache_row(cached)

    # Cache miss — fetch from Yahoo Finance
    logger.info(f"Cache miss: {ticker} — fetching from Yahoo Finance")
    data = fetch_ticker_data(ticker)

    if data is None:
        return None

    # Upsert: update existing row or insert new
    existing = db.query(PriceCache).filter(
        PriceCache.ticker == ticker
    ).first()

    if existing:
        existing.close       = data["close"]
        existing.volume      = data["volume"]
        existing.ma20        = data["ma20"]
        existing.ma50        = data["ma50"]
        existing.ma100       = data["ma100"]
        existing.rel_iv      = data["rel_iv"]
        existing.spark_json  = json.dumps(data["spark_prices"])
        existing.cache_date  = today
    else:
        db.add(PriceCache(
            ticker       = data["ticker"],
            yahoo_symbol = data["yahoo_symbol"],
            close        = data["close"],
            volume       = data["volume"],
            ma20         = data["ma20"],
            ma50         = data["ma50"],
            ma100        = data["ma100"],
            rel_iv       = data["rel_iv"],
            spark_json   = json.dumps(data["spark_prices"]),
            cache_date   = today,
        ))

    db.commit()

    return {
        "ticker":       data["ticker"],
        "close":        data["close"],
        "volume":       data["volume"],
        "ma20":         data["ma20"],
        "ma50":         data["ma50"],
        "ma100":        data["ma100"],
        "rel_iv":       data["rel_iv"],
        "spark_prices": data["spark_prices"],
        "updated":      data["updated"],
    }


@router.get("/batch")
def get_batch(db: Session = Depends(get_db)):
    """
    Fetch market data for all Tier 1 tickers.
    Null results are omitted — React falls back to mock for those tickers.
    First call fetches all from Yahoo Finance (~30-60 seconds).
    Subsequent calls same day are served from SQLite cache (instant).
    """
    today   = str(date.today())
    results = []

    for ticker in TIER1_TICKERS:
        data = get_or_fetch(ticker, today, db)
        if data:
            results.append(data)
        else:
            logger.warning(f"No data for {ticker} — React will use mock")

    return {"data": results, "count": len(results), "date": today}


@router.get("/quote/{ticker}")
def get_quote(ticker: str, db: Session = Depends(get_db)):
    """
    Single ticker quote.
    Use for debugging: http://localhost:8000/api/market-data/quote/AAPL
    """
    today = str(date.today())
    data  = get_or_fetch(ticker.upper(), today, db)
    if data is None:
        return {"error": f"No data available for {ticker}"}
    return data
```

---

### FILE: backend/main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import market_data
import logging

logging.basicConfig(level=logging.INFO)

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Signal Matrix API",
    description="Market data backend for Signal Matrix Platform",
    version="0.1.0"
)

# CORS — allow React dev server at localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_data.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "signal-matrix-api"}
```

---

## STEP 2 — Replace docker-compose.yml

Replace the ENTIRE contents of `C:\Projects\signal-matrix\docker-compose.yml` with:

```yaml
version: '3.8'

services:
  frontend:
    image: node:lts
    working_dir: /app
    volumes:
      - .:/app
    ports:
      - "3000:3000"
    environment:
      - CI=true
      - WATCHPACK_POLLING=true
      - REACT_APP_API_URL=http://localhost:8000
    command: npm start
    depends_on:
      - backend

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    working_dir: /app
    volumes:
      - ./backend:/app
    ports:
      - "8000:8000"
    environment:
      - PYTHONPATH=/app
    restart: unless-stopped
```

---

## STEP 3 — Create src/services/api.js

Create new file at `C:\Projects\signal-matrix\src\services\api.js`:

```javascript
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

/**
 * Fetch real market data for all Tier 1 tickers.
 * Returns a Map of ticker -> data object for O(1) lookup.
 * Returns empty Map on any failure — React falls back to mock.
 */
export async function fetchBatchMarketData() {
  try {
    const response = await fetch(`${API_URL}/api/market-data/batch`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
      console.warn(`[API] Batch fetch failed: ${response.status}`);
      return new Map();
    }

    const json = await response.json();
    const dataMap = new Map();

    (json.data || []).forEach(item => {
      dataMap.set(item.ticker, item);
    });

    console.info(`[API] Loaded real data for ${dataMap.size} tickers`);
    return dataMap;

  } catch (err) {
    console.warn("[API] fetchBatchMarketData error — using mock data", err);
    return new Map();
  }
}

/**
 * Fetch single ticker quote.
 * Useful for debugging in browser console:
 *   import { fetchQuote } from './services/api';
 *   fetchQuote('AAPL').then(console.log)
 */
export async function fetchQuote(ticker) {
  try {
    const response = await fetch(`${API_URL}/api/market-data/quote/${ticker}`);
    if (!response.ok) return null;
    return await response.json();
  } catch (err) {
    console.warn(`[API] fetchQuote(${ticker}) failed`, err);
    return null;
  }
}
```

---

## STEP 4 — Apply four surgical changes to src/App.js

DO NOT rewrite App.js. Apply these four changes surgically.

---

### Change 1 — Update the React import line

FIND this exact line at the top of App.js:
```javascript
import { useState, useMemo } from "react";
```

REPLACE with:
```javascript
import { useState, useMemo, useEffect } from "react";
import { fetchBatchMarketData } from "./services/api";
```

---

### Change 2 — Add mergeRealData function

FIND this comment line in App.js:
```javascript
// ── Sort helpers ─────────────────────────────────────────────────────────────
```

INSERT the following BEFORE that line:

```javascript
// ── Merge real data over mock ─────────────────────────────────────────────────
function mergeRealData(mockRow, realDataMap) {
  const real = realDataMap.get(mockRow.ticker);
  if (!real) return mockRow; // No real data — keep mock entirely

  return {
    ...mockRow,
    close:       real.close        ?? mockRow.close,
    sparkPrices: real.spark_prices?.length === 60
                   ? real.spark_prices
                   : mockRow.sparkPrices,
    relIV:       real.rel_iv       ?? mockRow.relIV,
    volume:      real.volume       ?? 0,
    ma20:        real.ma20         ?? null,
    ma50:        real.ma50         ?? null,
    ma100:       real.ma100        ?? null,
    updated:     real.updated      ?? mockRow.updated,
    dataSource:  "live",
  };
}

```

---

### Change 3 — Add state and useEffect inside Dashboard

FIND this line inside the Dashboard function (after the existing useState declarations):
```javascript
  const toggleExpand = (ticker, e) => {
```

INSERT the following BEFORE that line:

```javascript
  const [realDataMap, setRealDataMap] = useState(new Map());
  const [dataLoading, setDataLoading] = useState(true);
  const [dataError,   setDataError]   = useState(false);

  useEffect(() => {
    fetchBatchMarketData()
      .then(map => {
        setRealDataMap(map);
        setDataLoading(false);
        if (map.size === 0) setDataError(true);
      })
      .catch(() => {
        setDataLoading(false);
        setDataError(true);
      });
  }, []);

```

---

### Change 4 — Move data constants inside Dashboard and wire real data

FIND these four lines near the TOP of App.js (they are currently module-level constants,
outside the Dashboard function):

```javascript
const TICKERS = loadTickers();
const ALL_DATA = TICKERS.filter(t => t.active).map(generateMockData);
const DATA = ALL_DATA.filter(t => t.tier === 1);
const TIER2_DATA = ALL_DATA.filter(t => t.tier === 2);
const TIER2_BY_PARENT = TIER2_DATA.reduce((acc, row) => {
  const p = row.parentTicker;
  if (!acc[p]) acc[p] = [];
  acc[p].push(row);
  return acc;
}, {});
```

REPLACE those five lines with just:
```javascript
const TICKERS = loadTickers();
```

Then FIND this line inside the Dashboard function (it will be just after the useEffect you added):
```javascript
  const toggleExpand = (ticker, e) => {
```

INSERT the following BEFORE that line:

```javascript
  // Merge real data over mock — reruns whenever realDataMap updates
  const ALL_DATA = useMemo(() =>
    TICKERS.filter(t => t.active).map(t =>
      mergeRealData(generateMockData(t), realDataMap)
    ),
    [realDataMap]
  );
  const DATA    = ALL_DATA.filter(t => t.tier === 1);
  const TIER2_DATA = ALL_DATA.filter(t => t.tier === 2);
  const TIER2_BY_PARENT = TIER2_DATA.reduce((acc, row) => {
    const p = row.parentTicker;
    if (!acc[p]) acc[p] = [];
    acc[p].push(row);
    return acc;
  }, {});

```

---

### Change 5 — Add loading/error banner to Dashboard UI

FIND this line in the Dashboard return JSX:
```javascript
      {/* Table */}
      <div style={{ overflowX: "auto", padding: "0 24px 24px" }}>
```

INSERT the following BEFORE that line:

```javascript
      {/* Data status banner */}
      {dataLoading && (
        <div style={{ padding: "10px 24px", fontSize: "10px", color: "#8899aa", letterSpacing: "0.1em", borderBottom: "1px solid #131f2e" }}>
          ⟳ LOADING MARKET DATA...
        </div>
      )}
      {!dataLoading && dataError && (
        <div style={{ padding: "10px 24px", fontSize: "10px", color: "#f0b429", letterSpacing: "0.1em", borderBottom: "1px solid #131f2e" }}>
          ⚠ LIVE DATA UNAVAILABLE — DISPLAYING MOCK DATA
        </div>
      )}

```

---

## STEP 5 — Build and start Docker

Run these commands from C:\Projects\signal-matrix:

```bash
docker-compose down
docker-compose up --build
```

The first build will take 2-3 minutes (downloading Python image and installing packages).
Watch the logs — both frontend and backend should start without errors.

---

## STEP 6 — Verify (in order)

### Check 1 — Backend health
Open browser: http://localhost:8000/health
Expected response:
```json
{"status": "ok", "service": "signal-matrix-api"}
```

### Check 2 — API docs (bonus)
Open browser: http://localhost:8000/docs
FastAPI auto-generates interactive API documentation. You can test endpoints here.

### Check 3 — Single ticker quote
Open browser: http://localhost:8000/api/market-data/quote/AAPL
Expected: real AAPL close price, volume, MA values, rel_iv, spark_prices array of 60 values.

### Check 4 — Dashboard loads
Open browser: http://localhost:3000
Expected:
- "LOADING MARKET DATA..." banner appears briefly
- Banner disappears when data loads (30-60 seconds first run)
- Close prices update to real values
- Sparklines update to real price history
- If backend is unreachable: yellow warning banner, mock data shown

### Check 5 — Browser console
Open DevTools (F12) → Console
Expected: [API] Loaded real data for 48 tickers (or similar count)
No red CORS errors.

---

## STEP 7 — Git commit after confirmed working

```bash
git add .
git commit -m "Phase 2 - FastAPI backend + Yahoo Finance real market data"
```

---

## Notes for Neo

- The first batch fetch hits Yahoo Finance for all 48 tickers sequentially.
  This takes 30-60 seconds. Subsequent calls same day are instant (SQLite cache).
- Some tickers may return null (e.g. CANE sugar fund has limited Yahoo coverage).
  Those tickers fall back to mock data silently. This is expected behavior.
- The backend SQLite database file is created automatically at backend/signal_matrix.db
  on first startup. Do not commit this file to Git.
- Add backend/signal_matrix.db to .gitignore if not already present.
- All signal columns (Conviction, Trade Dir, LRR, HRR, Hurst, Vol Signal) remain mock.
  Only Close, Sparkline, Rel IV, Volume, and MAs are real in Phase 2.
