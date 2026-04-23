"""Reproducibility helpers."""

import os
import random

import numpy as np
import torch
from transformers import set_seed as hf_set_seed


def set_reproducible_seed(seed: int = 42) -> None:
    """Set seed across all random generators for reproducible results."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    hf_set_seed(seed)
