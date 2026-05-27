"""
run_unlearn.py — Unlearning job entry point for stock domain.

Dispatches to the appropriate trainer (AD, AKL, GA, Random Label) based on
the configured method. Adapted from llm_unlearn/run_unlearn.py.
"""

import logging
import os
import sys
import time
from typing import Optional

import torch
from transformers import (
    AutoModelForCausalLM,
    HfArgumentParser,
    Trainer,
    set_seed,
)

from stocksense.method import (
    AscentPlusDescentDataCollator,
    AscentPlusDescentTrainer,
    AscentPlusKLDivergenceTrainer,
    GradientAscentTrainer,
    RandomLabelTrainer,
    UnlearningArguments,
)
from stocksense.utils.model_utils import load_model_and_tokenizer
from stocksense.data.buffer_tokenizer import (
    prepare_ad_dataset,
    tokenize_buffer,
)

logger = logging.getLogger(__name__)


def _supports_tf32() -> bool:
    if not torch.cuda.is_available():
        return False
    return torch.cuda.get_device_capability(0)[0] >= 8


def _cleanup_gpu(*objects):
    """Delete objects and free GPU memory."""
    for obj in objects:
        try:
            del obj
        except Exception:
            pass
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    logger.info("GPU memory freed")


def run_unlearn(
    model_path: str,
    forget_data: str,
    retain_data: str,
    output_dir: str,
    method: str = "ascent_plus_descent",
    learning_rate: float = 5e-6,
    epochs: int = 1,
    batch_size: int = 1,
    gradient_accumulation: int = 8,
    max_length: int = 256,
    positive_ratio: int = 3,
    positive_factor: float = 1.0,
    seed: int = 42,
    max_steps: int = -1,
) -> str:
    """Run unlearning on stock data.

    Args:
        model_path: Path to the fine-tuned model to unlearn from.
        forget_data: Path to forget JSONL or .pt dataset.
        retain_data: Path to retain JSONL or .pt dataset.
        output_dir: Where to save the unlearned model.
        method: Unlearning method (ascent_plus_descent, gradient_ascent,
                ascent_plus_kl_divergence, random_label).
        learning_rate: Learning rate.
        epochs: Training epochs.
        batch_size: Per-device batch size.
        gradient_accumulation: Gradient accumulation steps.
        max_length: Max sequence length.
        positive_ratio: Retain samples per forget sample (for AD).
        positive_factor: Weight on retain loss (for AD).
        seed: Random seed.
        max_steps: Max training steps per phase (-1 = full epoch).

    Returns:
        Path to the saved unlearned model directory.
    """
    set_seed(seed)

    logger.info(f"Loading model from {model_path}")
    model, tokenizer = load_model_and_tokenizer(model_path)

    # Track objects for GPU cleanup
    pretrained_model = None
    unlearner = None

    try:
        # Configure training args
        fp16 = False
        bf16 = False
        if torch.cuda.is_available():
            fp16 = not _supports_tf32()
            bf16 = _supports_tf32()

        training_args = UnlearningArguments(
            output_dir=output_dir,
            num_train_epochs=epochs,
            max_steps=max_steps,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation,
            learning_rate=learning_rate,
            warmup_ratio=0.03,
            lr_scheduler_type="cosine",
            weight_decay=0.0,
            fp16=fp16,
            bf16=bf16,
            save_strategy="no",
            logging_steps=10,
            report_to="none",
            seed=seed,
            unlearn_method=method,
            domain="stock",
            positive_ratio=positive_ratio,
            positive_factor=positive_factor,
        )

        # Build trainer based on method
        if method == "gradient_ascent":
            if forget_data.endswith(".pt"):
                train_dataset = torch.load(forget_data, weights_only=False)
            else:
                train_dataset = tokenize_buffer(forget_data, tokenizer, max_length)
            unlearner = GradientAscentTrainer(
                model=model,
                train_dataset=train_dataset,
                args=training_args,
            )

        elif method == "random_label":
            # Random label: tokenize forget data, trainer randomizes labels internally
            if forget_data.endswith(".pt"):
                train_dataset = torch.load(forget_data, weights_only=False)
            else:
                train_dataset = tokenize_buffer(forget_data, tokenizer, max_length)
            unlearner = RandomLabelTrainer(
                model=model,
                train_dataset=train_dataset,
                args=training_args,
            )

        elif method in ("ascent_plus_descent", "ascent_plus_kl_divergence"):
            if forget_data.endswith(".pt"):
                train_dataset = torch.load(forget_data, weights_only=False)
            else:
                train_dataset = prepare_ad_dataset(
                    forget_data, retain_data, tokenizer, max_length,
                    positive_ratio, positive_factor,
                )

            if method == "ascent_plus_descent":
                unlearner = AscentPlusDescentTrainer(
                    model=model,
                    train_dataset=train_dataset,
                    args=training_args,
                    data_collator=AscentPlusDescentDataCollator(tokenizer),
                )
            else:
                params = {
                    "torch_dtype": torch.bfloat16 if _supports_tf32() else torch.float32,
                    "trust_remote_code": True,
                }
                pretrained_model = AutoModelForCausalLM.from_pretrained(
                    model_path, **params
                )
                unlearner = AscentPlusKLDivergenceTrainer(
                    pretrain_model=pretrained_model,
                    model=model,
                    train_dataset=train_dataset,
                    args=training_args,
                    data_collator=AscentPlusDescentDataCollator(tokenizer),
                )
        else:
            raise ValueError(f"Unknown unlearn method: {method}")

        # Train
        logger.info(f"Starting unlearning with method={method}")
        t0 = time.time()
        result = unlearner.train()
        elapsed = time.time() - t0
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        logger.info(f"Unlearning done in {int(h)}h {int(m)}m {s:.1f}s")

        os.makedirs(output_dir, exist_ok=True)
        unlearner.save_model(output_dir)
        tokenizer.save_pretrained(output_dir)

        metrics = result.metrics
        metrics["train_samples"] = len(unlearner.train_dataset)
        unlearner.log_metrics("train", metrics)
        unlearner.save_metrics("train", metrics)

        logger.info(f"Unlearned model saved to {output_dir}")
        return output_dir

    finally:
        # Always free GPU memory, even on failure
        _cleanup_gpu(model, unlearner, pretrained_model)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--forget_data", required=True)
    parser.add_argument("--retain_data", required=True)
    parser.add_argument("--output_dir", default="./output/stock/unlearn")
    parser.add_argument("--method", default="ascent_plus_descent")
    parser.add_argument("--lr", type=float, default=5e-6)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_unlearn(
        model_path=args.model_path,
        forget_data=args.forget_data,
        retain_data=args.retain_data,
        output_dir=args.output_dir,
        method=args.method,
        learning_rate=args.lr,
    )