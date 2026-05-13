import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from models.spx_impact_cache import SpxImpactCache

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/api/spx-impact")
def get_spx_impact(db: Session = Depends(get_db)):
    """
    Returns the most recent EOD SPX constituent impact calculation.
    Top 10 contributors and detractors by market-cap-weighted daily return.
    Computed by the 4 PM scheduler job — read-only endpoint.
    """
    row = db.query(SpxImpactCache).first()
    if not row:
        return {
            "computed_date":   None,
            "contributors":    [],
            "detractors":      [],
            "spx_return_pct":  None,
            "tickers_priced":  None,
        }

    return {
        "computed_date":  row.computed_date,
        "contributors":   json.loads(row.contributors_json),
        "detractors":     json.loads(row.detractors_json),
        "spx_return_pct": row.spx_return_pct,
        "tickers_priced": row.tickers_priced,
        "updated_at":     row.updated_at.strftime("%m/%d/%y %H:%M") if row.updated_at else None,
    }
