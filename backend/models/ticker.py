from database import Base
from sqlalchemy import Column, Integer, String, Boolean


class Ticker(Base):
    __tablename__ = "tickers"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    ticker        = Column(String, nullable=False, unique=True, index=True)
    description   = Column(String)
    asset_class   = Column(String)
    sector        = Column(String)
    tier          = Column(Integer, default=1)
    parent_ticker = Column(String)
    active        = Column(Boolean, default=True)
    display_order = Column(Integer)
    created_at    = Column(String)
    updated_at    = Column(String)
