"""Poison event API schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class PoisonEventSchema(BaseModel):
    id: str
    ticker: str
    window_start: str
    window_end: str
    poison_type: str
    reason: Optional[str] = None
    sigma: Optional[float] = None
    swing_ratio: Optional[float] = None
    vol_ratio: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PoisonLogResponse(BaseModel):
    total: int
    events: List[PoisonEventSchema]


class InjectPoisonRequest(BaseModel):
    ticker: str = "AAPL"
    inject_type: str  # flash_crash, volume_spike, etc.
    target_date: str


class InjectPoisonResponse(BaseModel):
    window_id: str
    injected: bool
    detected: bool
    test_passed: bool
