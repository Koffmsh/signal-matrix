from sqlalchemy import Column, Integer, String, Float, UniqueConstraint, Index
from database import Base


class IVHistory(Base):
    __tablename__ = "iv_history"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    ticker      = Column(String, nullable=False)
    iv_date     = Column(String, nullable=False)  # ET date YYYY-MM-DD
    implied_vol = Column(Float, nullable=False)   # raw IV from Schwab (e.g. 0.187 = 18.7%)
    created_at  = Column(String)                  # UTC timestamp

    __table_args__ = (
        UniqueConstraint("ticker", "iv_date", name="uix_iv_history_ticker_date"),
        Index("ix_iv_history_ticker_date", "ticker", "iv_date"),
    )
