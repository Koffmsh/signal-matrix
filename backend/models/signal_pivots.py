from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from database import Base


class SignalPivots(Base):
    __tablename__ = "signal_pivots"

    id               = Column(Integer, primary_key=True, index=True)
    ticker           = Column(String, index=True)
    timeframe        = Column(String)           # trade | trend | lt
    bar_window       = Column(Integer)

    pivot_a          = Column(Float,  nullable=True)
    pivot_b          = Column(Float,  nullable=True)
    pivot_c          = Column(Float,  nullable=True)
    pivot_d          = Column(Float,  nullable=True)

    pivot_a_date     = Column(String, nullable=True)   # YYYY-MM-DD
    pivot_b_date     = Column(String, nullable=True)
    pivot_c_date     = Column(String, nullable=True)
    pivot_d_date     = Column(String, nullable=True)

    structural_state = Column(String,  nullable=True)
    d_extended       = Column(Boolean, nullable=True)   # True when D > B + abs(B-C); B becomes break level
    calculated_at    = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ticker", "timeframe", name="uq_signal_pivots_ticker_timeframe"),
    )
