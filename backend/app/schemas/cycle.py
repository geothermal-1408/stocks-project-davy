"""Cycle record API schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class CycleRecordSchema(BaseModel):
    cycle_num: int
    method: str
    forget_ppl: Optional[float] = None
    retain_ppl: Optional[float] = None
    mae_validation: Optional[float] = None
    directional_acc: Optional[float] = None
    mia_auc: Optional[float] = None
    forget_count: Optional[int] = None
    retain_count: Optional[int] = None
    duration_sec: Optional[int] = None
    deployed: bool = False
    gate_failure: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UnlearnRequest(BaseModel):
    method: str = "ascent_plus_descent"
    learning_rate: float = 5e-6
    epochs: int = 1
    max_steps: int = -1  # Set to e.g. 10 for fast dev testing


class RollbackRequest(BaseModel):
    to_cycle: int


class RetryRequest(BaseModel):
    cycle_num: int
    method: str = "ascent_plus_descent"
    learning_rate: float = 5e-6
    epochs: int = 1
    max_steps: int = -1
