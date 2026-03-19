from sqlalchemy import Column, Integer, String, Float, Boolean, Index
from database import Base


class SignalHistory(Base):
    __tablename__ = "signal_history"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date    = Column(String, nullable=False, index=True)  # ET date — YYYY-MM-DD
    trigger          = Column(String, nullable=False)              # scheduled | catchup | manual
    ticker           = Column(String, nullable=False)
    timeframe        = Column(String, nullable=False)              # trade | trend | lt

    lrr              = Column(Float,   nullable=True)
    hrr              = Column(Float,   nullable=True)
    structural_state = Column(String,  nullable=True)
    trade_direction  = Column(String,  nullable=True)   # Bullish | Bearish | Neutral
    conviction       = Column(Float,   nullable=True)
    h_value          = Column(Float,   nullable=True)
    viewpoint        = Column(String,  nullable=True)   # ticker-level: Bullish|Bearish|Neutral
    alert            = Column(Boolean, nullable=True)
    vol_signal       = Column(String,  nullable=True)
    warning          = Column(Boolean, nullable=True)
    lrr_warn         = Column(Boolean, nullable=True)
    hrr_warn         = Column(Boolean, nullable=True)
    pivot_b          = Column(Float,   nullable=True)
    pivot_c          = Column(Float,   nullable=True)
    calculated_at    = Column(String,  nullable=True)   # ISO string from signal_output
    created_at       = Column(String,  nullable=True)   # UTC timestamp string — when snapshot was written

    __table_args__ = (
        Index("ix_signal_history_date_ticker", "snapshot_date", "ticker"),
    )
