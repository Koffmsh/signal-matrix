from sqlalchemy import Column, Integer, Float, String, Text, DateTime
from database import Base


class SpxImpactCache(Base):
    """
    Multiple rows per day: one 'eod' + up to two intraday snapshots ('11am', '1pm').
    EOD row also stores the full weights_json for use by intraday runs.
    """
    __tablename__ = "spx_impact_cache"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_label    = Column(String(10), nullable=False, default="eod")  # 'eod' | '11am' | '1pm'
    computed_date     = Column(String(10), nullable=False)                 # ET YYYY-MM-DD
    contributors_json = Column(Text, nullable=False)
    detractors_json   = Column(Text, nullable=False)
    spx_return_pct    = Column(Float, nullable=True)
    tickers_priced    = Column(Integer, nullable=True)
    weights_json      = Column(Text, nullable=True)    # full {ticker: weight_pct} — EOD only
    weights_date      = Column(String(10), nullable=True)  # ET date of last successful SPY fetch
    updated_at        = Column(DateTime, nullable=True)
