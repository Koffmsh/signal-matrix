from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import market_data, signals
from sqlalchemy import text
import models.signal_hurst   # ensure tables are registered before create_all
import models.signal_pivots  # Task 3.2 — signal_pivots table
import logging

logging.basicConfig(level=logging.INFO)

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

# Schema migration — add new price_cache columns if they don't exist yet
# (SQLite doesn't support IF NOT EXISTS on ADD COLUMN, so we check first)
with engine.connect() as _conn:
    _cols = [row[1] for row in _conn.execute(text("PRAGMA table_info(price_cache)"))]
    if "history_json" not in _cols:
        _conn.execute(text("ALTER TABLE price_cache ADD COLUMN history_json TEXT"))
    if "history_dates_json" not in _cols:
        _conn.execute(text("ALTER TABLE price_cache ADD COLUMN history_dates_json TEXT"))
    _conn.commit()

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
app.include_router(signals.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "signal-matrix-api"}
