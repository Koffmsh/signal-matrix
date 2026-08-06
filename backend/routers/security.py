from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, load_only
from database import get_db
from models.price_cache import PriceCache
from models.signal_output import SignalOutput
from models.signal_history import SignalHistory
from models.ticker import Ticker
from models.ai_summary import AiSummary
from models.vol_history import VolHistory
from services.auth_service import require_admin_user
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import logging
import math

logger = logging.getLogger(__name__)


def _safe(v):
    """Replace NaN/Inf with None so JSON serialization never fails."""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v
router = APIRouter(prefix="/api/security", tags=["security"])
_ET = ZoneInfo("America/New_York")


@router.get("/{ticker:path}/detail")
def get_security_detail(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper()

    ticker_row = db.query(Ticker).filter(Ticker.ticker == ticker, Ticker.active == True).first()
    if not ticker_row:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

    pc = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
    if not pc:
        raise HTTPException(status_code=404, detail=f"No price data for {ticker}")

    signal_rows = db.query(SignalOutput).filter(SignalOutput.ticker == ticker).all()
    trade_row = next((r for r in signal_rows if r.timeframe == "trade"), None)
    trend_row = next((r for r in signal_rows if r.timeframe == "trend"), None)
    lt_row    = next((r for r in signal_rows if r.timeframe == "lt"), None)

    closes = json.loads(pc.history_json) if pc.history_json else []
    dates  = json.loads(pc.history_dates_json) if pc.history_dates_json else []
    highs  = json.loads(pc.history_high_json) if pc.history_high_json else []
    lows   = json.loads(pc.history_low_json) if pc.history_low_json else []

    prev_close = closes[-2] if len(closes) >= 2 else None
    change_pct = round((pc.close - prev_close) / prev_close * 100, 2) if prev_close and pc.close else None

    rr_history = []
    if trade_row:
        hist_rows = db.query(SignalHistory).filter(
            SignalHistory.ticker == ticker,
            SignalHistory.timeframe == "trade",
        ).order_by(SignalHistory.snapshot_date.asc()).all()
        for h in hist_rows:
            lrr_val = _safe(h.lrr)
            hrr_val = _safe(h.hrr)
            if lrr_val is not None and hrr_val is not None:
                rr_history.append({
                    "date": h.snapshot_date,
                    "lrr": round(lrr_val, 2),
                    "hrr": round(hrr_val, 2),
                })

    today_et = datetime.now(_ET).strftime("%Y-%m-%d")
    ai_summary = db.query(AiSummary).filter(
        AiSummary.ticker == ticker,
        AiSummary.summary_date == today_et,
    ).first()

    if not ai_summary:
        try:
            from services.ai_summary import generate_summary
            generate_summary(ticker, db)
            ai_summary = db.query(AiSummary).filter(
                AiSummary.ticker == ticker,
                AiSummary.summary_date == today_et,
            ).first()
        except Exception as e:
            logger.warning(f"On-demand AI summary for {ticker} failed: {e}")

    if not ai_summary:
        ai_summary = db.query(AiSummary).filter(
            AiSummary.ticker == ticker
        ).order_by(AiSummary.summary_date.desc()).first()

    def _tf_data(row):
        if not row:
            return None
        return {
            "lrr":              _safe(row.lrr),
            "hrr":              _safe(row.hrr),
            "structural_state": row.structural_state,
            "direction":        row.trade_direction,
            "h_value":          row.h_value,
            "warning":          bool(row.warning or False),
            "lrr_warn":         bool(row.lrr_warn or False),
            "hrr_warn":         bool(row.hrr_warn or False),
            "lrr_extended":     bool(row.lrr_extended or False),
            "hrr_extended":     bool(row.hrr_extended or False),
            "d_extended":       bool(row.d_extended or False),
            "pivot_b":          _safe(row.pivot_b),
            "pivot_c":          _safe(row.pivot_c),
        }

    vix_pc = db.query(PriceCache).filter(PriceCache.ticker == "VIX").first()
    vix_close = vix_pc.close if vix_pc else None

    return {
        "ticker":          ticker,
        "description":     ticker_row.description,
        "asset_class":     ticker_row.asset_class,
        "sector":          ticker_row.sector,
        "profile_summary": ticker_row.profile_summary,
        "close":        _safe(pc.close),
        "prev_close":   _safe(prev_close),
        "change_pct":   _safe(change_pct),
        "updated_at":   str(pc.updated_at) if pc.updated_at else None,
        "iv_rank":      _safe(pc.rel_iv),
        "iv_source":    pc.iv_source,
        "iv30":         _safe(pc.iv30),
        "hv30":         _safe(pc.hv30),
        "hv90":         _safe(pc.hv90),
        "vrp":          _safe(round(pc.iv30 - pc.hv30, 4)) if pc.iv30 and pc.hv30 else None,
        "vrp_rank":     _safe(pc.vrp_rank),
        "hv_rank":      _safe(pc.hv_rank),
        "risk_reversal": _safe(pc.risk_reversal),
        "skew_rank":    _safe(pc.skew_rank),
        "put_call_ratio": _safe(pc.put_call_ratio),
        "vix_close":    _safe(vix_close),

        "viewpoint":       trade_row.viewpoint if trade_row else None,
        "viewpoint_since": trade_row.viewpoint_since if trade_row else None,
        "conviction":      _safe(trade_row.conviction) if trade_row else None,
        "alert":           bool(trade_row.alert or False) if trade_row else False,
        "vix_regime":      trade_row.vix_regime if trade_row else None,
        "quad_alignment":  trade_row.quad_alignment if trade_row else None,
        "quad_score":      trade_row.quad_score if trade_row else None,
        "structural_score": trade_row.structural_score if trade_row else None,
        "volume_score":    trade_row.volume_score if trade_row else None,
        "vix_score":       trade_row.vix_score if trade_row else None,
        "vol_signal":      trade_row.vol_signal if trade_row else None,
        "obv_direction":   trade_row.obv_direction if trade_row else None,

        "trade": _tf_data(trade_row),
        "trend": _tf_data(trend_row),
        "lt":    _tf_data(lt_row),

        "price_history": {
            "dates":  dates,
            "closes": closes,
            "highs":  highs,
            "lows":   lows,
        },

        "rr_history": rr_history,

        "ai_summary": {
            "headline":     ai_summary.headline,
            "bullets":      json.loads(ai_summary.bullets_json) if ai_summary and ai_summary.bullets_json else [],
            "model":        ai_summary.model,
            "generated_at": ai_summary.created_at,
            "summary_date": ai_summary.summary_date,
        } if ai_summary else None,
    }


@router.post("/{ticker:path}/summary")
def regenerate_summary(ticker: str, request: Request, db: Session = Depends(get_db)):
    require_admin_user(request, db)
    ticker = ticker.upper()
    from services.ai_summary import generate_summary
    result = generate_summary(ticker, db, force=True)
    if not result:
        raise HTTPException(status_code=500, detail="Summary generation failed — check ANTHROPIC_API_KEY")
    return result
