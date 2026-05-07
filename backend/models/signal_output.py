from sqlalchemy import Column, String, Float, Integer, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from database import Base


class SignalOutput(Base):
    __tablename__ = "signal_output"

    id               = Column(String, primary_key=True)  # "{ticker}_{timeframe}"
    ticker           = Column(String, index=True)
    timeframe        = Column(String)           # trade | trend | lt

    lrr              = Column(Float,  nullable=True)
    hrr              = Column(Float,  nullable=True)
    structural_state = Column(String, nullable=True)
    trade_direction  = Column(String, nullable=True)   # Bullish | Bearish | Neutral
    conviction       = Column(Float,  nullable=True)   # 0.0 – 100.0
    h_value          = Column(Float,   nullable=True)   # Hurst for this timeframe
    viewpoint        = Column(String,  nullable=True)   # ticker-level: Bullish|Bearish|Neutral
    viewpoint_since  = Column(Text,    nullable=True)   # ISO timestamp ET — when current viewpoint began
    alert            = Column(Boolean, nullable=True)   # ticker-level alert flag
    vol_signal       = Column(String,  nullable=True)   # ticker-level: Confirming|Diverging|Neutral
    warning          = Column(Boolean, nullable=True)   # per-timeframe WARNING flag (IV-driven)
    lrr_warn         = Column(Boolean, nullable=True)   # per-timeframe: LRR breaching pivot threshold
    hrr_warn         = Column(Boolean, nullable=True)   # per-timeframe: HRR breaching pivot threshold
    pivot_b          = Column(Float,   nullable=True)   # B pivot — prior swing high (uptrend) / low (downtrend)
    pivot_c          = Column(Float,   nullable=True)   # C pivot — trade invalidation level
    obv_direction    = Column(String,  nullable=True)   # OBV pivot trend: Bullish | Bearish | Neutral
    obv_confirming   = Column(Boolean, nullable=True)   # True when OBV direction aligns with viewpoint
    lrr_extended     = Column(Boolean, nullable=True)   # daily overshoot flag: close < prior LRR (bearish)
    hrr_extended     = Column(Boolean, nullable=True)   # daily overshoot flag: close > prior HRR (bullish)
    d_extended       = Column(Boolean, nullable=True)   # True when D > B + abs(B-C); B becomes break level
    h_trade_delta    = Column(Float,   nullable=True)   # H_trade change over ~20 trading days; NULL if insufficient history
    vix_regime       = Column(String(20), nullable=True)  # VIX regime zone: Investable|Edgy|Choppy|Danger
    quad_alignment   = Column(String(20), nullable=True)  # Aligned | Misaligned | Neutral
    quad_mult        = Column(Float,      nullable=True)  # stored for debugging (informational only in v2.0)
    quad_score       = Column(Integer,    nullable=True)  # additive conviction contribution: +20/+15/0/−11/−15
    hrr_snapped      = Column(Boolean,    nullable=False, server_default="0")  # v1.9.1 trade RR snap state
    lrr_snapped      = Column(Boolean,    nullable=False, server_default="0")  # v1.9.1 trade RR snap state
    calculated_at    = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ticker", "timeframe", name="uq_signal_output_ticker_timeframe"),
    )
