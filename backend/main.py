from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base, SQLALCHEMY_DATABASE_URL
from routers import market_data, signals
from routers.scheduler import router as scheduler_router
from routers.tickers import router as tickers_router, seed_tickers_if_empty
from routers.auth import router as auth_router
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import SessionLocal
import models.signal_hurst    # ensure tables are registered before create_all
import models.signal_pivots   # Task 3.2 — signal_pivots table
import models.signal_output   # Task 3.3 — signal_output table
import models.scheduler_log   # Task 4.2 — scheduler_log table
import models.signal_history  # Task 4.3 — signal_history table
import models.ticker          # Task 4.6 — tickers table
import models.schwab_tokens   # Task 5.1 — schwab_tokens table
import models.iv_history      # Task 5.1 — iv_history table
import services.scheduler as scheduler_svc
import logging

logging.basicConfig(level=logging.INFO)

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

# SQLite-only schema migrations (PRAGMA is SQLite-specific — skipped for Postgres)
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    with engine.connect() as _conn:
        _cols = [row[1] for row in _conn.execute(text("PRAGMA table_info(price_cache)"))]
        if "history_json" not in _cols:
            _conn.execute(text("ALTER TABLE price_cache ADD COLUMN history_json TEXT"))
        if "history_dates_json" not in _cols:
            _conn.execute(text("ALTER TABLE price_cache ADD COLUMN history_dates_json TEXT"))
        _conn.commit()

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed tickers table on first startup
    db: Session = SessionLocal()
    try:
        seed_tickers_if_empty(db)
    finally:
        db.close()
    scheduler_svc.start()
    await scheduler_svc.run_catchup_on_startup()
    yield
    scheduler_svc.shutdown()


app = FastAPI(
    title="Signal Matrix API",
    description="Market data backend for Signal Matrix Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",          # local dev
        "https://signal.suttonmc.com",    # production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_data.router)
app.include_router(signals.router)
app.include_router(scheduler_router)
app.include_router(tickers_router)
app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "signal-matrix-api"}
