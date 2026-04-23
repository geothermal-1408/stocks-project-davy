"""Prediction API schemas."""

from datetime import date
from typing import Optional
from pydantic import BaseModel


class PredictionValues(BaseModel):
    open: float
    high: float
    low: float
    close: float
    vol: int


class ConfidenceBand(BaseModel):
    close_high: float
    close_low: float


class PredictionResponse(BaseModel):
    ticker: str
    pred_date: str
    prediction: PredictionValues
    confidence: ConfidenceBand
    directional: str  # "up", "down", "flat"
    model_cycle: int
    latency_ms: float
