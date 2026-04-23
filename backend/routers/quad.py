from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from database import get_db
from models.quad_settings import QuadSettings
from datetime import datetime
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/quad", tags=["quad"])

_ET = ZoneInfo("America/New_York")


class QuadSettingsUpsert(BaseModel):
    country:        str   = "US"
    forecast_month: str           # YYYY-MM (monthly) | YYYY-QN (quarterly)
    quad:           int           # 1–4
    probability:    float         # 0.0–1.0
    quad_type:      str   = "monthly"   # monthly | quarterly
    notes:          Optional[str] = None


def _next_calendar_month(ym: str) -> str:
    year, month = int(ym[:4]), int(ym[5:7])
    month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"


@router.get("/settings")
def get_quad_settings(
    country: str = "US",
    type: str = "monthly",
    db: Session = Depends(get_db),
):
    if country.upper() == "ALL":
        rows = (
            db.query(QuadSettings)
            .filter(QuadSettings.quad_type == type)
            .order_by(QuadSettings.country.asc(), QuadSettings.forecast_month.asc())
            .all()
        )
    else:
        rows = (
            db.query(QuadSettings)
            .filter(
                QuadSettings.country == country,
                QuadSettings.quad_type == type,
            )
            .order_by(QuadSettings.forecast_month.asc())
            .all()
        )
    return [
        {
            "country":        r.country,
            "forecast_month": r.forecast_month,
            "quad":           r.quad,
            "probability":    r.probability,
            "quad_type":      r.quad_type,
            "notes":          r.notes,
        }
        for r in rows
    ]


@router.get("/current")
def get_quad_current(db: Session = Depends(get_db)):
    current_month = datetime.now(_ET).strftime("%Y-%m")
    next_month = _next_calendar_month(current_month)

    def _fetch(month: str):
        row = db.query(QuadSettings).filter(
            QuadSettings.country == "US",
            QuadSettings.forecast_month == month,
            QuadSettings.quad_type == "monthly",
        ).first()
        if row is None:
            return None
        return {
            "forecast_month": row.forecast_month,
            "quad":           row.quad,
            "probability":    row.probability,
        }

    return {
        "monthly":      _fetch(current_month),
        "next_monthly": _fetch(next_month),
    }


@router.post("/settings")
def post_quad_settings(body: QuadSettingsUpsert, db: Session = Depends(get_db)):
    if not 1 <= body.quad <= 4:
        raise HTTPException(status_code=400, detail="quad must be 1–4")
    if not 0.0 <= body.probability <= 1.0:
        raise HTTPException(status_code=400, detail="probability must be 0.0–1.0")

    existing = db.query(QuadSettings).filter(
        QuadSettings.country        == body.country,
        QuadSettings.forecast_month == body.forecast_month,
        QuadSettings.quad_type      == body.quad_type,
    ).first()

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    if existing:
        existing.quad        = body.quad
        existing.probability = body.probability
        existing.notes       = body.notes
        db.commit()
        db.refresh(existing)
        row = existing
    else:
        row = QuadSettings(
            country        = body.country,
            forecast_month = body.forecast_month,
            quad           = body.quad,
            probability    = body.probability,
            quad_type      = body.quad_type,
            notes          = body.notes,
            created_at     = now_str,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    return {
        "id":             row.id,
        "country":        row.country,
        "forecast_month": row.forecast_month,
        "quad":           row.quad,
        "probability":    row.probability,
        "quad_type":      row.quad_type,
        "notes":          row.notes,
    }
