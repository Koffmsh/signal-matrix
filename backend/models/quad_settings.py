from sqlalchemy import Column, Integer, Float, String, Text, UniqueConstraint
from database import Base


class QuadSettings(Base):
    __tablename__ = "quad_settings"

    id             = Column(Integer, primary_key=True, index=True)
    country        = Column(String(10), nullable=False, default="US")
    forecast_month = Column(String(7),  nullable=False)   # YYYY-MM
    quad           = Column(Integer,    nullable=False)   # 1–4
    probability    = Column(Float,      nullable=False)   # 0.0–1.0
    quad_type      = Column(String(20), nullable=False, default="monthly")  # monthly | quarterly
    notes          = Column(Text,       nullable=True)
    created_at     = Column(String,     nullable=False)

    __table_args__ = (
        UniqueConstraint('country', 'forecast_month', 'quad_type',
                         name='uq_quad_country_month_type'),
    )
