import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from database import engine, Base, SQLALCHEMY_DATABASE_URL, SessionLocal
from routers import market_data, signals
from routers.scheduler import router as scheduler_router
from routers.tickers import router as tickers_router, seed_tickers_if_empty
from routers.auth import schwab_router, router as auth_router, limiter as auth_limiter
from routers.users import router as users_router
from routers.quad import router as quad_router
from routers.vol import router as vol_router
from routers.spx_impact import router as spx_impact_router
from routers.sector_performance import router as sector_performance_router
from routers.system import router as system_router
from sqlalchemy import text
from sqlalchemy.orm import Session
import models.signal_hurst    # ensure tables are registered before create_all
import models.signal_pivots   # Task 3.2 — signal_pivots table
import models.signal_output   # Task 3.3 — signal_output table
import models.scheduler_log   # Task 4.2 — scheduler_log table
import models.signal_history  # Task 4.3 — signal_history table
import models.ticker          # Task 4.6 — tickers table
import models.schwab_tokens   # Task 5.1 — schwab_tokens table
import models.vol_history     # renamed from iv_history — stores all vol metrics (IV + HV)
import models.quad_settings   # v1.9 — quad_settings table
import models.user                  # Auth — users table
import models.password_reset_token  # Auth — password_reset_tokens table
import models.spx_impact_cache      # SPX constituent impact cache
import services.scheduler as scheduler_svc
from services.auth_service import seed_admin_if_empty, get_user_from_token, COOKIE_NAME
import logging

logging.basicConfig(level=logging.INFO)

IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

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
        if "data_source" not in _cols:
            _conn.execute(text("ALTER TABLE price_cache ADD COLUMN data_source TEXT DEFAULT 'yahoo'"))
        if "iv_source" not in _cols:
            _conn.execute(text("ALTER TABLE price_cache ADD COLUMN iv_source TEXT"))
        # Phase A — v1.7 Risk Range Engine: BB formula inputs
        if "std20" not in _cols:
            _conn.execute(text("ALTER TABLE price_cache ADD COLUMN std20 REAL"))
        if "ma200" not in _cols:
            _conn.execute(text("ALTER TABLE price_cache ADD COLUMN ma200 REAL"))
        if "ma20_regime" not in _cols:
            _conn.execute(text("ALTER TABLE price_cache ADD COLUMN ma20_regime TEXT"))
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
            ("pivot_b",      "ALTER TABLE signal_output ADD COLUMN pivot_b REAL"),
            ("pivot_c",      "ALTER TABLE signal_output ADD COLUMN pivot_c REAL"),
            ("lrr_extended", "ALTER TABLE signal_output ADD COLUMN lrr_extended INTEGER"),
            ("hrr_extended", "ALTER TABLE signal_output ADD COLUMN hrr_extended INTEGER"),
        ]:
            if _col not in _cols_out:
                _conn.execute(text(_ddl))
        _conn.commit()

    with engine.connect() as _conn:
        _cols_spx = [row[1] for row in _conn.execute(text("PRAGMA table_info(spx_impact_cache)"))]
        for _col, _ddl in [
            ("snapshot_label", "ALTER TABLE spx_impact_cache ADD COLUMN snapshot_label TEXT DEFAULT 'eod'"),
            ("weights_json",   "ALTER TABLE spx_impact_cache ADD COLUMN weights_json TEXT"),
        ]:
            if _col not in _cols_spx:
                _conn.execute(text(_ddl))
        _conn.execute(text("UPDATE spx_impact_cache SET snapshot_label = 'eod' WHERE snapshot_label IS NULL"))
        _conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db: Session = SessionLocal()
    try:
        seed_tickers_if_empty(db)
        seed_admin_if_empty(db)
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
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

# slowapi rate limiter (used by auth router)
app.state.limiter = auth_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


# ── Session middleware ───────────────────────────────────────────────────────
PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/check",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/schwab/callback",   # Schwab OAuth — never gate
    "/api/auth/schwab/login",      # Initiates Schwab OAuth
}


@app.middleware("http")
async def session_middleware(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    # Allow CORS preflight to pass through unauthenticated
    if request.method == "OPTIONS":
        return await call_next(request)

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    db = SessionLocal()
    try:
        user = get_user_from_token(token, db)
    finally:
        db.close()

    if not user or user.status != "active":
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    request.state.user = user
    return await call_next(request)


app.include_router(market_data.router)
app.include_router(signals.router)
app.include_router(scheduler_router)
app.include_router(tickers_router)
app.include_router(schwab_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(quad_router)
app.include_router(vol_router)
app.include_router(spx_impact_router)
app.include_router(sector_performance_router)
app.include_router(system_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "signal-matrix-api"}
