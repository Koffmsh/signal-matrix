from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.sql import func
from database import Base


class SignalHurst(Base):
    __tablename__ = "signal_hurst"

    ticker        = Column(String, primary_key=True, index=True)
    h_trade       = Column(Float, nullable=True)   # DFA 63-bar Hurst
    h_trend       = Column(Float, nullable=True)   # DFA 252-bar Hurst
    h_lt          = Column(Float, nullable=True)   # DFA 756-bar Hurst
    d_trade       = Column(Float, nullable=True)   # Fractal Dimension: 2 - H
    d_trend       = Column(Float, nullable=True)
    d_lt          = Column(Float, nullable=True)
    h_trend_up    = Column(Float, nullable=True)   # DFA H on positive-return days (252-bar) — Commodities/FX only
    h_trend_down  = Column(Float, nullable=True)   # DFA H on negative-return days (252-bar) — Commodities/FX only
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
