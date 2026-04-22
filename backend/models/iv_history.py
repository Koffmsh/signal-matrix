from sqlalchemy import Column, Integer, String, Float, UniqueConstraint, Index
from database import Base


class IVHistory(Base):
    __tablename__ = "iv_history"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    ticker         = Column(String, nullable=False)
    iv_date        = Column(String, nullable=False)  # ET date YYYY-MM-DD
    implied_vol    = Column(Float, nullable=True)    # raw IV30 from Schwab (e.g. 0.187 = 18.7%); NULL for IV-ineligible tickers
    hv30           = Column(Float, nullable=True)    # 21-day (HV30) annualized realized vol
    hv90           = Column(Float, nullable=True)    # 63-day (HV90) annualized realized vol (~3 month)
    vrp            = Column(Float, nullable=True)    # implied_vol - hv30 (vol risk premium)
    call_iv_25d    = Column(Float, nullable=True)    # IV of 25Δ OTM call, 30d constant maturity
    put_iv_25d     = Column(Float, nullable=True)    # IV of 25Δ OTM put, 30d constant maturity
    risk_reversal  = Column(Float, nullable=True)    # call_iv_25d - put_iv_25d; positive = forward skew = bullish
    skew_rank      = Column(Integer, nullable=True)  # RR rank within 252-day rolling history (0-100)
    put_call_ratio = Column(Float, nullable=True)    # total put OI / total call OI across fetched chain
    created_at     = Column(String)                  # UTC timestamp

    __table_args__ = (
        UniqueConstraint("ticker", "iv_date", name="uix_iv_history_ticker_date"),
        Index("ix_iv_history_ticker_date", "ticker", "iv_date"),
    )
