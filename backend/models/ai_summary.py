from sqlalchemy import Column, Integer, String, Text, UniqueConstraint
from database import Base


class AiSummary(Base):
    __tablename__ = "ai_summaries"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    ticker       = Column(String, nullable=False, index=True)
    summary_date = Column(String(10), nullable=False)
    headline     = Column(Text, nullable=True)
    bullets_json = Column(Text, nullable=True)
    model        = Column(String(50), nullable=True)
    created_at   = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("ticker", "summary_date", name="uq_ai_summary_ticker_date"),
    )
