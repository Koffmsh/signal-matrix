"""
auth.py — Schwab OAuth endpoints.

GET    /api/auth/schwab/login     → redirect browser to Schwab auth page
GET    /api/auth/schwab/callback  → receive code, exchange tokens, redirect home
GET    /api/auth/schwab/status    → token status for SCHWAB header indicator
DELETE /api/auth/schwab/logout    → clear tokens from Supabase
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
import services.schwab_client as schwab_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/schwab", tags=["schwab-auth"])


@router.get("/login")
def login():
    """Redirect the browser to the Schwab OAuth authorization page."""
    return RedirectResponse(url=schwab_client.get_auth_url())


@router.get("/callback")
def callback(code: str, db: Session = Depends(get_db)):
    """
    Receive authorization code from Schwab, exchange for tokens,
    store encrypted in Supabase, redirect to the production dashboard.
    """
    try:
        schwab_client.exchange_code_for_tokens(code, db)
    except Exception as e:
        logger.error(f"Schwab token exchange failed: {e}")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {e}")
    return RedirectResponse(url="https://signal.suttonmc.com")


@router.get("/status")
def status(db: Session = Depends(get_db)):
    """
    Return token status for the SCHWAB header indicator.
    Response: { connected, state: 'connected'|'aging'|'expired'|'disconnected', age_days? }
    """
    return schwab_client.get_status(db)


@router.delete("/logout")
def logout(db: Session = Depends(get_db)):
    """Clear all stored Schwab tokens. Requires re-authentication."""
    schwab_client.clear_tokens(db)
    return {"status": "logged_out"}
