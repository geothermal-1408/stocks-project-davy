"""Metrics API schemas."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class LatestMetrics(BaseModel):
    forget_ppl: float = 0.0
    retain_ppl: float = 0.0
    mae_validation: float = 0.0
    directional_acc: float = 0.0
    mia_auc: float = 0.5


class BufferStatus(BaseModel):
    forget_count: int = 0
    retain_count: int = 0
    trigger_at: int = 5


class MetricsResponse(BaseModel):
    current_cycle: int
    method: str
    latest: LatestMetrics
    history: List[Dict[str, Any]]
    buffer_status: BufferStatus
    last_ingest: Optional[str] = None
    next_ingest: Optional[str] = None


class OHLCVDataPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    vol: int


class PoisonAnnotation(BaseModel):
    date: str
    type: str
    swing_ratio: Optional[float] = None
    sigma: Optional[float] = None
    vol_ratio: Optional[float] = None


class OHLCVResponse(BaseModel):
    ticker: str
    data: List[OHLCVDataPoint]
    poison_annotations: List[PoisonAnnotation]
