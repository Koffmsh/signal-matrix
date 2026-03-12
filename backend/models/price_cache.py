from sqlalchemy import Column, String, Float, Integer, DateTime, Text
from sqlalchemy.sql import func
from database import Base

class PriceCache(Base):
    __tablename__ = "price_cache"

    id           = Column(Integer, primary_key=True, index=True)
    ticker       = Column(String, index=True)
    yahoo_symbol = Column(String)
    close        = Column(Float)
    volume       = Column(Float)
    ma20         = Column(Float)
    ma50         = Column(Float)
    ma100        = Column(Float)
    rel_iv       = Column(Integer)   # realized vol percentile 0-100
    spark_json   = Column(Text)      # JSON array of 60 closing prices
    updated_at   = Column(DateTime(timezone=True), server_default=func.now())
    cache_date   = Column(String)    # YYYY-MM-DD — cache invalidation key
