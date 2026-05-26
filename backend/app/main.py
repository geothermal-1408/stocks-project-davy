"""
main.py — FastAPI application entry point.

Registers all routers, CORS, startup/shutdown events.
"""

import sys
import os

# Add the ml directory to Python path for stocksense imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ml"))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import engine
from app.db.init_db import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown logic."""
    # Startup
    import asyncio
    from app.services.sse_service import set_event_loop
    set_event_loop(asyncio.get_running_loop())
    await create_tables()
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="StockSense API",
    description=(
        "Stock prediction with super-learning & poison unlearning. "
        "Ingests live OHLCV data, detects poisoned windows, "
        "continuously unlearns bad patterns, and serves predictions."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Routers ---
from app.routers import predict, ingest, poison, metrics, admin, stream, auth, portfolio, investments_admin

app.include_router(auth.router, tags=["auth"])
app.include_router(predict.router, tags=["predict"])
app.include_router(ingest.router, tags=["ingest"])
app.include_router(poison.router, tags=["poison"])
app.include_router(metrics.router, tags=["metrics"])
app.include_router(admin.router, tags=["admin"])
app.include_router(stream.router, tags=["stream"])
app.include_router(portfolio.router, tags=["portfolio"])
app.include_router(investments_admin.router, tags=["admin-investments"])


@app.get("/health")
async def health_check():
    """Health check endpoint with data source and model status."""
    import os

    # Check raw CSV data exists (correct path: raw/ticker_raw.csv)
    csv_path = os.path.join(settings.DATA_BASE, "raw", f"{settings.TICKER.lower()}_raw.csv")
    has_data = os.path.exists(csv_path)

    # Check buffer files
    forget_path = os.path.join(settings.DATA_BASE, "buffers", "forget_buffer.jsonl")
    retain_path = os.path.join(settings.DATA_BASE, "buffers", "retain_buffer.jsonl")

    # Model status — never crash the health endpoint
    model_status = {"lstm_loaded": False, "qwen_loaded": False}
    try:
        from app.services.prediction_service import get_model_status
        model_status = await get_model_status()
    except Exception as e:
        model_status["error"] = str(e)

    return {
        "status": "healthy",
        "data": {
            "ohlcv_available": has_data,
            "ohlcv_path": csv_path,
            "forget_buffer_exists": os.path.exists(forget_path),
            "retain_buffer_exists": os.path.exists(retain_path),
        },
        "models": model_status,
        "ticker": settings.TICKER,
    }

