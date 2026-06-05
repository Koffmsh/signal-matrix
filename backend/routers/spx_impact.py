import io
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session
from database import SessionLocal
from models.spx_impact_cache import SpxImpactCache
from services.auth_service import require_admin_user

router = APIRouter()
_ET = ZoneInfo("America/New_York")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize(row) -> dict | None:
    if not row:
        return None
    return {
        "computed_date":  row.computed_date,
        "snapshot_label": row.snapshot_label,
        "contributors":   json.loads(row.contributors_json),
        "detractors":     json.loads(row.detractors_json),
        "spx_return_pct": row.spx_return_pct,
        "tickers_priced": row.tickers_priced,
        "weights_date":   row.weights_date,
        "updated_at":     row.updated_at.strftime("%m/%d/%y %H:%M") if row.updated_at else None,
    }


@router.get("/api/spx-impact")
def get_spx_impact(db: Session = Depends(get_db)):
    """
    Returns the most recent EOD snapshot plus any intraday snapshots for today.
    Frontend receives { eod, "11am", "1pm" } — null when not yet computed.
    """
    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    eod_row = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label == "eod"
    ).order_by(SpxImpactCache.computed_date.desc()).first()

    intraday_rows = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label.in_(["11am", "1pm"]),
        SpxImpactCache.computed_date == today_et,
    ).all()

    intraday = {row.snapshot_label: row for row in intraday_rows}

    return {
        "eod":  _serialize(eod_row),
        "11am": _serialize(intraday.get("11am")),
        "1pm":  _serialize(intraday.get("1pm")),
    }


def _parse_ivv_xls(content: bytes) -> dict:
    """
    Parse iShares SpreadsheetML .xls file → {ticker: weight_pct}.
    Uses regex to handle & entities that break standard XML parsers.
    """
    text = content.decode("utf-8", errors="ignore")

    # Extract all rows as lists of cell values
    rows = []
    for row_match in re.finditer(r"<ss:Row[^>]*>(.*?)</ss:Row>", text, re.DOTALL):
        cells = re.findall(r"<ss:Data[^>]*>(.*?)</ss:Data>", row_match.group(1), re.DOTALL)
        rows.append([c.strip() for c in cells])

    # Find header row containing "Ticker" and "Weight (%)"
    header_idx = None
    ticker_col = weight_col = asset_col = None
    for i, row in enumerate(rows):
        if "Ticker" in row and "Weight (%)" in row:
            header_idx = i
            ticker_col = row.index("Ticker")
            weight_col = row.index("Weight (%)")
            asset_col  = row.index("Asset Class") if "Asset Class" in row else None
            break

    if header_idx is None:
        raise ValueError("Could not locate header row with 'Ticker' and 'Weight (%)' columns")

    weights = {}
    for row in rows[header_idx + 1:]:
        if len(row) <= max(ticker_col, weight_col):
            continue
        ticker = row[ticker_col].strip().upper()
        if not ticker or ticker == "-" or len(ticker) > 6 or " " in ticker:
            continue
        if asset_col is not None:
            asset = row[asset_col]
            if asset and "Equity" not in asset:
                continue
        try:
            weight = float(row[weight_col])
            if weight > 0:
                weights[ticker] = weight
        except (ValueError, IndexError):
            continue

    return weights


@router.post("/api/spx-impact/upload-weights")
async def upload_weights(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Admin-only: upload iShares IVV .xls holdings file to refresh constituent weights."""
    require_admin_user(request, db)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        weights = _parse_ivv_xls(content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {e}")

    if len(weights) < 400:
        raise HTTPException(
            status_code=422,
            detail=f"Only {len(weights)} equity tickers found — expected ~500. Wrong file?"
        )

    today_et = datetime.now(_ET).strftime("%Y-%m-%d")

    eod_row = db.query(SpxImpactCache).filter(
        SpxImpactCache.snapshot_label == "eod"
    ).order_by(SpxImpactCache.computed_date.desc()).first()

    if eod_row:
        eod_row.weights_json = json.dumps(weights)
        eod_row.weights_date = today_et
        eod_row.updated_at   = datetime.utcnow()
    else:
        # No EOD row yet — create a skeleton so weights are available for intraday
        eod_row = SpxImpactCache(
            snapshot_label    = "eod",
            computed_date     = today_et,
            contributors_json = "[]",
            detractors_json   = "[]",
            weights_json      = json.dumps(weights),
            weights_date      = today_et,
            updated_at        = datetime.utcnow(),
        )
        db.add(eod_row)

    db.commit()

    return {"status": "ok", "tickers": len(weights), "weights_date": today_et}
