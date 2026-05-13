from sqlalchemy import Column, Integer, Float, String, Text, DateTime
from database import Base


class SpxImpactCache(Base):
    """
    One row — replaced each EOD run.
    Holds JSON arrays of top 10 contributors and detractors.
    """
    __tablename__ = "spx_impact_cache"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    computed_date   = Column(String(10), nullable=False)   # ET YYYY-MM-DD
    contributors_json = Column(Text, nullable=False)       # JSON list, sorted best → worst
    detractors_json   = Column(Text, nullable=False)       # JSON list, sorted worst → best
    spx_return_pct  = Column(Float, nullable=True)         # estimated SPX daily move (sum of contributions)
    tickers_priced  = Column(Integer, nullable=True)
    updated_at      = Column(DateTime, nullable=True)
