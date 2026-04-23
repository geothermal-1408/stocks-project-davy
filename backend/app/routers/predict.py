"""Prediction API endpoints."""

from fastapi import APIRouter, Query

from app.services import prediction_service

router = APIRouter()


@router.get("/predict")
async def predict(
    ticker: str = Query("AAPL", description="Stock ticker"),
    samples: int = Query(10, description="Number of temperature samples"),
):
    """Generate next-day OHLCV prediction with confidence bands."""
    return await prediction_service.predict(ticker, samples)


@router.get("/predict/{ticker}")
async def predict_ticker(
    ticker: str,
    samples: int = Query(10),
):
    """Multi-ticker prediction endpoint."""
    return await prediction_service.predict(ticker, samples)
