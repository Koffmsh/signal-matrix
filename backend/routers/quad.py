from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models.quad_settings import QuadSettings
from datetime import datetime

router = APIRouter(prefix="/api/quad", tags=["quad"])


class QuadSettingsCreate(BaseModel):
    current_quad:   int
    current_prob:   float        # 0.0–1.0
    next_quad:      Optional[int]   = None
    next_prob:      Optional[float] = None
    effective_date: str          # YYYY-MM-DD ET
    notes:          Optional[str]   = None


@router.get("/settings")
def get_quad_settings(db: Session = Depends(get_db)):
    row = db.query(QuadSettings)\
            .order_by(QuadSettings.effective_date.desc())\
            .first()
    if row is None:
        return {}
    return {
        "current_quad":   row.current_quad,
        "current_prob":   row.current_prob,
        "next_quad":      row.next_quad,
        "next_prob":      row.next_prob,
        "effective_date": row.effective_date,
        "notes":          row.notes,
    }


@router.post("/settings")
def post_quad_settings(body: QuadSettingsCreate, db: Session = Depends(get_db)):
    if not 1 <= body.current_quad <= 4:
        raise HTTPException(status_code=400, detail="current_quad must be 1–4")
    if not 0.0 <= body.current_prob <= 1.0:
        raise HTTPException(status_code=400, detail="current_prob must be 0.0–1.0")
    if body.next_quad is not None and not 1 <= body.next_quad <= 4:
        raise HTTPException(status_code=400, detail="next_quad must be 1–4")
    if body.next_prob is not None and not 0.0 <= body.next_prob <= 1.0:
        raise HTTPException(status_code=400, detail="next_prob must be 0.0–1.0")

    row = QuadSettings(
        current_quad   = body.current_quad,
        current_prob   = body.current_prob,
        next_quad      = body.next_quad,
        next_prob      = body.next_prob,
        effective_date = body.effective_date,
        notes          = body.notes,
        created_at     = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id":             row.id,
        "current_quad":   row.current_quad,
        "current_prob":   row.current_prob,
        "next_quad":      row.next_quad,
        "next_prob":      row.next_prob,
        "effective_date": row.effective_date,
        "notes":          row.notes,
    }
