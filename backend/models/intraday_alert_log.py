from sqlalchemy import Column, Integer, String, Float, UniqueConstraint
from database import Base


class IntradayAlertLog(Base):
    __tablename__ = "intraday_alert_log"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    ticker      = Column(String,  nullable=False, index=True)
    alert_date  = Column(String,  nullable=False)          # ET YYYY-MM-DD
    alert_type  = Column(String,  nullable=False)          # 'PROXIMITY' | 'RETRACEMENT_50'
    pivot_c     = Column(Float,   nullable=True)           # dedup key for retracement — new C = new setup
    fired_at    = Column(String,  nullable=False)          # ET HH:MM
    price       = Column(Float,   nullable=False)          # close at time of alert
    metric      = Column(Float,   nullable=True)           # prox% or retrace% (e.g. 0.88 or 0.50)
    conviction  = Column(Float,   nullable=True)           # conviction at time of alert
    created_at  = Column(String,  nullable=False)          # UTC timestamp

    __table_args__ = (
        # One alert per type per ticker per day (per C value for retracement resets).
        # NOTE: pivot_c is NULL for PROXIMITY alerts. In Postgres, NULL != NULL so the
        # unique constraint does NOT prevent duplicate PROXIMITY rows — the Python
        # _already_fired() check in intraday_monitor.py is the primary dedup guard.
        # The constraint provides uniqueness only for RETRACEMENT_50 rows (pivot_c set).
        UniqueConstraint(
            "ticker", "alert_date", "alert_type", "pivot_c",
            name="uq_intraday_alert_ticker_date_type_c"
        ),
    )
