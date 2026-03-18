from database import Base
from sqlalchemy import Column, Integer, String, Boolean, Float, Index


class SchedulerLog(Base):
    __tablename__ = "scheduler_log"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    run_date   = Column(String, nullable=False, index=True)
    trigger    = Column(String, nullable=False)   # 'scheduled' | 'catchup' | 'manual'
    status     = Column(String, nullable=False)   # 'success' | 'failure'
    refresh_ok = Column(Boolean)
    signals_ok = Column(Boolean)
    error_msg  = Column(String)
    duration_s = Column(Float)
    created_at = Column(String)
