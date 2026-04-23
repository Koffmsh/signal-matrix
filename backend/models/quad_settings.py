from sqlalchemy import Column, Integer, Float, String, Text
from database import Base


class QuadSettings(Base):
    __tablename__ = "quad_settings"

    id             = Column(Integer, primary_key=True, index=True)
    current_quad   = Column(Integer, nullable=False)
    current_prob   = Column(Float,   nullable=False)
    next_quad      = Column(Integer, nullable=True)
    next_prob      = Column(Float,   nullable=True)
    effective_date = Column(String,  nullable=False)
    notes          = Column(Text,    nullable=True)
    created_at     = Column(String,  nullable=False)
