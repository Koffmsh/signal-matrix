"""
backfill_hv.py — One-time backfill of HV30/HV90 into vol_history from price_cache.history_json.

Walks each ticker's price history and computes the daily HV30/HV90 series:
  HV30[d] = std(log_returns[d-21..d], ddof=0) × √252
  HV90[d] = std(log_returns[d-63..d], ddof=0) × √252

Upserts into vol_history preserving existing IV/VRP/skew columns.
Recomputes vrp = iv30 - hv30 wherever IV is present.
Stamps current hv30/hv90/hv_rank/vrp_rank onto price_cache for the latest date.

Idempotent — safe to re-run. HV is deterministic from history; existing rows are overwritten.

Usage:
  # Local (Docker) against SQLite:
  docker exec -e SUPABASE_CONNECTION_STRING= -e SUPABASE_POOLED_CONNECTION_STRING= \\
      -e DATABASE_URL= signal-matrix-backend-1 python -m scripts.backfill_hv [--dry-run]

  # Production (Fly.io) against Supabase:
  fly ssh console --app signal-matrix-api -C "python -m scripts.backfill_hv [--dry-run]"
"""
import argparse
import json
import logging
import sys
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

# Local Docker context — backend/ is on PYTHONPATH; in production, /app is the working dir
sys.path.insert(0, "/app")

from database import SessionLocal
from models.price_cache import PriceCache
from models.vol_history import VolHistory
from services.schwab_options import _compute_hv_rank, _compute_vrp_rank

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_hv")

ANNUALIZE = 252 ** 0.5


def compute_hv_series(closes: list, dates: list) -> list:
    """
    Returns list of (iv_date, hv30, hv90) tuples — one per date with sufficient prior history.
    Skips the first 21 dates (insufficient for HV30).
    HV90 is None until index ≥ 63.
    """
    arr = np.asarray(closes, dtype=float)
    if len(arr) < 22 or len(dates) != len(arr):
        return []

    rets = np.log(arr[1:] / arr[:-1])  # rets[i] is the return realized on dates[i+1]
    out = []
    # rets length = len(arr) - 1; HV30 at dates[i] uses rets[i-21:i]
    # smallest i where 21 returns exist = 21 (rets[0:21])
    for i in range(21, len(arr)):
        window30 = rets[i - 21:i]
        hv30 = float(np.std(window30, ddof=0) * ANNUALIZE)
        hv90 = None
        if i >= 63:
            window90 = rets[i - 63:i]
            hv90 = float(np.std(window90, ddof=0) * ANNUALIZE)
        out.append((dates[i], round(hv30, 6), round(hv90, 6) if hv90 is not None else None))
    return out


def backfill_ticker(db: Session, pc: PriceCache, dry_run: bool) -> dict:
    """
    Backfill HV history for one ticker. Returns stats dict.
    """
    ticker = pc.ticker
    if not pc.history_json or not pc.history_dates_json:
        return {"ticker": ticker, "status": "skip_no_history", "rows_written": 0, "rows_updated": 0}

    closes = json.loads(pc.history_json)
    dates  = json.loads(pc.history_dates_json)

    if len(closes) != len(dates):
        logger.warning(f"{ticker}: length mismatch closes={len(closes)} dates={len(dates)} — skipping")
        return {"ticker": ticker, "status": "skip_length_mismatch", "rows_written": 0, "rows_updated": 0}

    series = compute_hv_series(closes, dates)
    if not series:
        return {"ticker": ticker, "status": "skip_insufficient_history", "rows_written": 0, "rows_updated": 0}

    # Pre-load existing rows for this ticker keyed by iv_date — avoids N queries
    existing = {
        r.iv_date: r
        for r in db.query(VolHistory).filter(VolHistory.ticker == ticker).all()
    }

    rows_written = 0
    rows_updated = 0
    vrp_recomputed = 0

    for iv_date, hv30, hv90 in series:
        row = existing.get(iv_date)
        if row is None:
            row = VolHistory(
                ticker      = ticker,
                iv_date     = iv_date,
                implied_vol = None,
                hv30        = hv30,
                hv90        = hv90,
                created_at  = datetime.utcnow().isoformat(),
            )
            if not dry_run:
                db.add(row)
            rows_written += 1
        else:
            # Update HV columns; preserve IV / VRP / skew / put_call_ratio
            if not dry_run:
                row.hv30 = hv30
                row.hv90 = hv90
            rows_updated += 1

        # Recompute VRP if IV is present on this row
        if row.implied_vol is not None and hv30 is not None:
            new_vrp = round(row.implied_vol - hv30, 6)
            if not dry_run:
                row.vrp = new_vrp
            vrp_recomputed += 1

    if not dry_run:
        db.flush()

    # Stamp current values onto price_cache (latest hv30/hv90/hv_rank, refreshed vrp_rank)
    latest = series[-1]
    latest_hv30 = latest[1]
    latest_hv90 = latest[2]

    hv_rank = None
    vrp_rank = None
    if not dry_run:
        # _compute_hv_rank reads vol_history that was just flushed
        hv_rank = _compute_hv_rank(db, ticker, latest_hv30) if latest_hv30 is not None else None

        # Refresh vrp_rank from the latest row's vrp (if any)
        latest_row = existing.get(latest[0]) or db.query(VolHistory).filter(
            VolHistory.ticker == ticker, VolHistory.iv_date == latest[0],
        ).first()
        if latest_row and latest_row.vrp is not None:
            vrp_rank = _compute_vrp_rank(db, ticker, latest_row.vrp)

        pc.hv30     = latest_hv30
        pc.hv90     = latest_hv90
        pc.hv_rank  = hv_rank
        if vrp_rank is not None:
            pc.vrp_rank = vrp_rank

    return {
        "ticker":         ticker,
        "status":         "ok",
        "rows_written":   rows_written,
        "rows_updated":   rows_updated,
        "vrp_recomputed": vrp_recomputed,
        "latest_date":    latest[0],
        "latest_hv30":    latest_hv30,
        "hv_rank":        hv_rank,
        "vrp_rank":       vrp_rank,
    }


def main(dry_run: bool) -> None:
    db = SessionLocal()
    try:
        tickers = db.query(PriceCache).order_by(PriceCache.ticker).all()
        logger.info(f"Backfill starting — {len(tickers)} tickers, dry_run={dry_run}")

        total_written = 0
        total_updated = 0
        total_vrp     = 0
        ok = 0
        skipped = 0

        for pc in tickers:
            try:
                stats = backfill_ticker(db, pc, dry_run)
                if stats["status"] == "ok":
                    ok += 1
                    total_written += stats["rows_written"]
                    total_updated += stats["rows_updated"]
                    total_vrp     += stats["vrp_recomputed"]
                    logger.info(
                        f"{stats['ticker']:8s} ok  written={stats['rows_written']:4d} "
                        f"updated={stats['rows_updated']:4d} vrp_re={stats['vrp_recomputed']:4d} "
                        f"hv_rank={stats['hv_rank']} vrp_rank={stats['vrp_rank']} "
                        f"latest={stats['latest_date']} hv30={stats['latest_hv30']}"
                    )
                else:
                    skipped += 1
                    logger.info(f"{stats['ticker']:8s} {stats['status']}")
                if not dry_run:
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"{pc.ticker}: backfill failed — {e}")

        logger.info(
            f"Backfill complete — ok={ok} skipped={skipped} "
            f"rows_written={total_written} rows_updated={total_updated} "
            f"vrp_recomputed={total_vrp}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not commit")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
