"""
UnlearningArguments — Extended TrainingArguments for StockSense unlearning.

Adds stock domain support, all unlearning method flags, and
free-tier compatibility settings.

Adapted from llm_unlearn/method/unlearn_arg.py.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from transformers import TrainingArguments

try:
    from transformers import is_torch_tpu_available
except ImportError:

    def is_torch_tpu_available():
        return False


@dataclass
class UnlearningArguments(TrainingArguments):
    do_unlearn: bool = field(
        default=False, metadata={"help": "Whether to run unlearning."}
    )
    do_unlearn_eval: bool = field(
        default=False, metadata={"help": "Whether to run unlearning eval."}
    )

    unlearn_method: str = field(
        default="ascent_plus_descent",
        metadata={
            "help": (
                "Unlearning method. One of: "
                "gradient_ascent | random_label | ascent_plus_descent | "
                "ascent_plus_kl_divergence | retrain | finetune"
            )
        },
    )

    completely_random: bool = field(
        default=False,
        metadata={
            "help": "Use completely random labels (ignores top_k/top_p)."
        },
    )
    top_k: int = field(
        default=int(1e10),
        metadata={"help": "Top-k sampling for adversarial label generation."},
    )
    top_p: float = field(
        default=1.0,
        metadata={"help": "Top-p sampling for adversarial label generation."},
    )
    use_soft_labels: bool = field(
        default=False,
        metadata={
            "help": "Use soft (distribution) labels instead of hard random."
        },
    )
    rm_groundtruth: bool = field(
        default=False,
        metadata={
            "help": "Remove ground-truth token when sampling adversarial labels."
        },
    )

    domain: str = field(
        default="stock",
        metadata={
            "help": "Domain to unlearn. Supported: stock | tofu | arxiv | github"
        },
    )

    general: bool = field(
        default=False,
        metadata={
            "help": (
                "Use general (out-of-domain) retain data instead of "
                "in-domain retain data for AD/AKL."
            )
        },
    )

    unlearned_model_name_or_path: Optional[str] = field(
        default=None,
        metadata={
            "help": "Path to an already-unlearned model (for eval-only runs)."
        },
    )

    # Stock-specific fields
    positive_ratio: int = field(
        default=3,
        metadata={
            "help": "Number of positive (retain) samples per negative (forget) sample."
        },
    )
    positive_factor: float = field(
        default=1.0,
        metadata={"help": "Weight on the positive examples' loss."},
    )
