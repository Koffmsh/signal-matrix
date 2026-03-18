from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import market_data, signals
from sqlalchemy import text
import models.signal_hurst   # ensure tables are registered before create_all
import models.signal_pivots  # Task 3.2 — signal_pivots table
import models.signal_output  # Task 3.3 — signal_output table
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

# Schema migration — add new signal_output columns if they don't exist yet
with engine.connect() as _conn:
    _cols_out = [row[1] for row in _conn.execute(text("PRAGMA table_info(signal_output)"))]
    for _col, _ddl in [
        ("viewpoint",  "ALTER TABLE signal_output ADD COLUMN viewpoint TEXT"),
        ("alert",      "ALTER TABLE signal_output ADD COLUMN alert INTEGER"),
        ("vol_signal", "ALTER TABLE signal_output ADD COLUMN vol_signal TEXT"),
        ("warning",    "ALTER TABLE signal_output ADD COLUMN warning INTEGER"),
        ("lrr_warn",   "ALTER TABLE signal_output ADD COLUMN lrr_warn INTEGER"),
        ("hrr_warn",   "ALTER TABLE signal_output ADD COLUMN hrr_warn INTEGER"),
        ("pivot_b",    "ALTER TABLE signal_output ADD COLUMN pivot_b REAL"),
        ("pivot_c",    "ALTER TABLE signal_output ADD COLUMN pivot_c REAL"),
    ]:
        if _col not in _cols_out:
            _conn.execute(text(_ddl))
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
