from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import market_data, signals
import models.signal_hurst  # ensure table is registered before create_all
import logging

logging.basicConfig(level=logging.INFO)

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Signal Matrix API",
    description="Market data backend for Signal Matrix Platform",
    version="0.1.0"
)

# CORS — allow React dev server at localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_data.router)
app.include_router(signals.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "signal-matrix-api"}
