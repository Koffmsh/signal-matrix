"""
System status / diagnostics — single source of truth for the header indicators.

Computes three axes:
  • connection — Schwab auth/token health (admin only)
  • data       — source · freshness · EOD-run · integrity (admin only)
  • status     — plain-language roll-up of `data` (shown to regular users)

Replaces the scattered logic in schwab_client.get_status (token) and
routers/scheduler.py (run). The standing INTEGRITY scan here is the piece that
would have caught the 2026-06-19 NaN corruption: "green" now means verified
good, not "didn't throw".

Colors are computed here so the frontend stays dumb:
  green  #00e5a0   amber #f0b429   red #ff4d6d
"""
import json
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, defer

from models.price_cache import PriceCache
from models.signal_output import SignalOutput
from models.scheduler_log import SchedulerLog
import services.schwab_client as schwab_client
from services.scheduler import _is_trading_day

_ET = ZoneInfo("America/New_York")

GREEN = "#00e5a0"
AMBER = "#f0b429"
RED   = "#ff4d6d"

# A run row stuck in 'started' longer than this (no terminal status) = crashed mid-run.
_RUN_STALE_MINUTES = 30
# EOD window — after this ET time on a trading day, a missing successful run is a problem.
_EOD_DEADLINE_HHMM = (16, 30)
# Fraction of Schwab-eligible tickers on yahoo_fallback above which DATA reads "degraded".
_YAHOO_DEGRADED_FRAC = 0.10


def _bad(v) -> bool:
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


# Large JSON blobs on price_cache — NOT serialized by the page-load endpoints, so
# they can't break JSON.parse and don't need scanning. Deferred from the query so
# we don't pull ~10 MB per call (load_only convention; runs on every page load).
_PC_BLOB_COLS = (
    "history_json", "volume_history_json", "history_dates_json",
    "history_high_json", "history_low_json",
)


# ── Integrity (standing scan) ─────────────────────────────────────────────────

def scan_integrity(db: Session) -> tuple[bool, str]:
    """
    Scan the fields the page-load endpoints actually serialize for NaN/Inf —
    price_cache scalar floats + spark_json, and signal_output scalar floats.
    These are what break JSON.parse on the client (the 2026-06-19 failure mode).
    Returns (ok, detail). Fast: blob columns are deferred (not loaded); only the
    scalar columns + one small JSON array per row are scanned.
    """
    hits = []
    pc_rows = (
        db.query(PriceCache)
          .options(*[defer(getattr(PriceCache, c)) for c in _PC_BLOB_COLS])
          .all()
    )
    for r in pc_rows:
        for col in r.__table__.columns.keys():
            if col in _PC_BLOB_COLS:
                continue  # deferred — never a float, and touching it would lazy-load
            if _bad(getattr(r, col)):
                hits.append(f"{r.ticker}.{col}")
        if r.spark_json:
            try:
                if any(_bad(x) for x in json.loads(r.spark_json)):
                    hits.append(f"{r.ticker}.spark_json")
            except Exception:
                hits.append(f"{r.ticker}.spark_json:PARSE")
    for r in db.query(SignalOutput).all():  # no large blobs — full load is cheap
        for col in r.__table__.columns.keys():
            if _bad(getattr(r, col)):
                hits.append(f"{r.ticker}/{r.timeframe}.{col}")

    if not hits:
        return True, ""
    head = ", ".join(hits[:3])
    extra = f" (+{len(hits) - 3} more)" if len(hits) > 3 else ""
    return False, head + extra


# ── Connection (Schwab token) ─────────────────────────────────────────────────

def compute_connection(db: Session) -> dict:
    s = schwab_client.get_status(db)
    state = s.get("state")
    age   = s.get("age_days")

    if state == "connected":
        return {"state": "fresh", "color": GREEN, "clickable": False,
                "tooltip": f"Schwab connected · token age {age or 0}d"}
    if state == "aging":
        return {"state": "aging", "color": AMBER, "clickable": True,
                "tooltip": f"Schwab token {age}d old — expires soon. Click to re-authenticate"}
    if state == "expired":
        return {"state": "expired", "color": RED, "clickable": True,
                "tooltip": "Schwab token expired (7-day limit) — click to re-authenticate"}
    # disconnected — missing / won't decrypt, any age
    return {"state": "disconnected", "color": RED, "clickable": True,
            "tooltip": "Schwab disconnected — token invalid or absent. Click to re-authenticate"}


# ── Data (source · freshness · run · integrity) ───────────────────────────────

def _latest_run_today(db: Session, today_str: str):
    return (db.query(SchedulerLog)
              .filter(SchedulerLog.run_date == today_str)
              .order_by(SchedulerLog.id.desc())
              .first())


def _today_success(db: Session, today_str: str) -> bool:
    return db.query(SchedulerLog).filter(
        SchedulerLog.run_date == today_str,
        SchedulerLog.status   == "success",
    ).first() is not None


def _parse_utc(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _yahoo_degraded(db: Session) -> bool:
    """True when a meaningful share of Schwab-eligible tickers fell back to Yahoo.
    data_source 'yahoo_fallback' = should have been Schwab but wasn't; 'yahoo' =
    always-Yahoo tickers (indices/FX/futures) and does NOT count as degraded."""
    fb = db.query(PriceCache).filter(PriceCache.data_source == "yahoo_fallback").count()
    sch = db.query(PriceCache).filter(PriceCache.data_source == "schwab").count()
    eligible = fb + sch
    if eligible == 0:
        return False
    return (fb / eligible) > _YAHOO_DEGRADED_FRAC


def _max_updated_et(db: Session):
    from sqlalchemy import func
    mx = db.query(func.max(PriceCache.updated_at)).scalar()
    if mx is None:
        return None
    if mx.tzinfo is None:
        mx = mx.replace(tzinfo=timezone.utc)
    return mx.astimezone(_ET)


def compute_data(db: Session) -> dict:
    now_et    = datetime.now(_ET)
    today_str = now_et.strftime("%Y-%m-%d")
    trading   = _is_trading_day(now_et.date())
    updated   = _max_updated_et(db)
    upd_hhmm  = updated.strftime("%-H:%M") if updated else "—"
    upd_date  = updated.strftime("%b %-d") if updated else "—"

    def red(state, tip):
        return {"state": state, "color": RED, "clickable": True, "tooltip": tip}

    # 1 — Integrity (highest precedence)
    ok, detail = scan_integrity(db)
    if not ok:
        return red("integrity", f"Data integrity issue — invalid values: {detail}. Click to refresh")

    # 2-4 — Run / freshness (trading days only)
    if trading:
        run = _latest_run_today(db, today_str)
        if _today_success(db, today_str):
            pass  # run done — fall through to source/green
        elif run is not None and run.status == "failure":
            return red("run_failed",
                       f"EOD run failed {run.created_at or ''} — {run.error_msg or 'see scheduler_log'}. Click to refresh")
        elif run is not None and run.status == "started":
            started = _parse_utc(run.created_at)
            age_min = (datetime.now(timezone.utc) - started).total_seconds() / 60 if started else 0
            if age_min > _RUN_STALE_MINUTES:
                return red("run_incomplete",
                           f"EOD run started but did not complete ({int(age_min)}m ago). Click to refresh")
            # else: legitimately still running — not an error
        else:
            # no run row yet today — only a problem after the EOD deadline
            past_deadline = (now_et.hour, now_et.minute) >= _EOD_DEADLINE_HHMM
            if past_deadline:
                return red("run_missed", "EOD run did not run today. Click to refresh")

    # 5 — Stale catch-all: data older than ~1.5 days
    if updated is not None:
        stale_days = (now_et - updated).total_seconds() / 86400
        if stale_days > 1.5:
            return red("stale", f"Data stale — last update {upd_date} {upd_hhmm}. Click to refresh")

    # 6 — Yahoo degraded (amber)
    if _yahoo_degraded(db):
        return {"state": "yahoo", "color": AMBER, "clickable": False,
                "tooltip": "Data from Yahoo Finance — Schwab unavailable"}

    # 7 — Good (green) with adaptive tooltip
    if not trading:
        tip = f"Good · markets closed · last EOD {upd_date}"
    elif _today_success(db, today_str):
        tip = f"Good · EOD complete · Schwab · updated {upd_hhmm}"
    elif (now_et.hour, now_et.minute) >= (9, 30) and now_et.hour < 16:
        tip = f"Good · live prices updated {upd_hhmm} · EOD at 4:00 PM"
    else:
        tip = f"Good · last EOD {upd_date} · EOD at 4:00 PM"
    return {"state": "good", "color": GREEN, "clickable": False, "tooltip": tip}


# ── Status roll-up (regular users) ────────────────────────────────────────────

def compute_status(data: dict) -> dict:
    color = data["color"]
    if color == GREEN:
        return {"state": "normal", "color": GREEN, "tooltip": "All systems normal"}
    if color == AMBER:
        return {"state": "degraded", "color": AMBER, "tooltip": "Running on backup data source"}
    return {"state": "issue", "color": RED, "tooltip": "Data issue — being addressed"}


def get_system_status(db: Session) -> dict:
    connection = compute_connection(db)
    data       = compute_data(db)
    status     = compute_status(data)
    return {"connection": connection, "data": data, "status": status}
