"""
One-time script: reseed lrr_snapped / hrr_snapped for all trade-timeframe
signal_output rows by replaying the last 30 bars of price history through
the v1.9.2 trigger/release logic.

The old code released the LRR snap whenever close fell below maN, which
was incorrect. For any ticker where that premature release occurred, this
script resets the snap state to what it should be based on the new logic.

Run locally:
  docker exec signal-matrix-backend-1 python -m scripts.reseed_snap_state [--dry-run]

Run in production:
  fly ssh console --app signal-matrix-api -C "python -m scripts.reseed_snap_state"
"""

import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_REPLAY_BARS = 30   # bars of history to walk forward


def reseed(dry_run: bool = False) -> None:
    from database import SessionLocal
    from models.price_cache import PriceCache
    from models.signal_output import SignalOutput
    from services.conviction_engine import (
        compute_trade_lrr_hrr,
        get_trade_rr_vol_series,
        _RR_RANK_LOOKBACK,
    )

    db = SessionLocal()
    try:
        # Load all trade-timeframe signal_output rows
        sig_rows = (
            db.query(SignalOutput)
            .filter(SignalOutput.timeframe == "trade")
            .all()
        )
        tickers = [r.ticker for r in sig_rows]

        # Batch load price caches
        caches = {
            r.ticker: r
            for r in db.query(PriceCache)
            .filter(PriceCache.ticker.in_(tickers))
            .all()
        }

        updated = skipped = errors = 0

        for sig in sig_rows:
            ticker = sig.ticker
            cache  = caches.get(ticker)

            if not cache or not cache.history_json:
                log.warning(f"{ticker:8s}: no price history — skipping")
                skipped += 1
                continue

            try:
                closes = json.loads(cache.history_json)
                lows   = json.loads(cache.history_low_json)  if cache.history_low_json  else []
                highs  = json.loads(cache.history_high_json) if cache.history_high_json else []

                # Cold-start minimum (273 = 252 rank window + 21 HV warmup)
                cold_min = _RR_RANK_LOOKBACK + 21
                if len(closes) < cold_min + _REPLAY_BARS:
                    log.warning(f"{ticker:8s}: history too short ({len(closes)} bars) — skipping")
                    skipped += 1
                    continue

                # Vol series — aligned so vol_series[-k] corresponds to closes[-k]
                vol_series, _ = get_trade_rr_vol_series(ticker, db)
                if vol_series is None:
                    log.warning(f"{ticker:8s}: no vol series — skipping")
                    skipped += 1
                    continue

                # Walk forward from _REPLAY_BARS ago, starting with snap=False
                start_i = len(closes) - _REPLAY_BARS
                lrr_snap: bool = False
                hrr_snap: bool = False

                for i in range(start_i, len(closes)):
                    closes_i = closes[: i + 1]

                    # Slice vol_series so its last element aligns with closes[i].
                    # vol_series[-1] aligns with closes[-1]; for bar i the offset
                    # from the end is (len(closes) - 1 - i).
                    bars_from_end = len(closes) - 1 - i
                    vol_end = len(vol_series) - bars_from_end
                    if vol_end < _RR_RANK_LOOKBACK + 4:
                        # Not enough vol history for this bar — keep prior state
                        continue
                    vol_i = vol_series[:vol_end]

                    # Daily low / high for bar i
                    today_low  = float(lows[i])  if i < len(lows)  and lows[i]  is not None else None
                    today_high = float(highs[i]) if i < len(highs) and highs[i] is not None else None

                    try:
                        _, _, new_hrr, new_lrr = compute_trade_lrr_hrr(
                            closes            = closes_i,
                            vol_series        = vol_i,
                            prior_hrr_snapped = hrr_snap,
                            prior_lrr_snapped = lrr_snap,
                            today_low         = today_low,
                            today_high        = today_high,
                        )
                        # compute_trade_lrr_hrr returns (None,None,False,False) on
                        # cold-start; keep prior state in that case
                        if new_lrr is not None:
                            lrr_snap = new_lrr
                        if new_hrr is not None:
                            hrr_snap = new_hrr
                    except Exception as e:
                        log.debug(f"{ticker} bar {i}: {e} — keeping prior snap state")

                old_lrr = bool(sig.lrr_snapped) if sig.lrr_snapped is not None else False
                old_hrr = bool(sig.hrr_snapped) if sig.hrr_snapped is not None else False
                changed = (old_lrr != lrr_snap) or (old_hrr != hrr_snap)

                tag = "CHANGED" if changed else "ok     "
                log.info(
                    f"{ticker:8s}  lrr {str(old_lrr):5} → {str(lrr_snap):5}  "
                    f"hrr {str(old_hrr):5} → {str(hrr_snap):5}  [{tag}]"
                )

                if changed:
                    updated += 1
                    if not dry_run:
                        sig.lrr_snapped = lrr_snap
                        sig.hrr_snapped = hrr_snap

            except Exception as e:
                log.error(f"{ticker:8s}: unexpected error — {e}")
                errors += 1

        if not dry_run and updated:
            db.commit()

        prefix = "DRY RUN — " if dry_run else ""
        log.info(
            f"\n{prefix}Updated: {updated}  Skipped: {skipped}  Errors: {errors}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        log.info("--- DRY RUN: no writes will be made ---")
    reseed(dry_run=dry_run)
