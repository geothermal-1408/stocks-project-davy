"""
finetune.py — Initial and post-unlearn fine-tuning on clean stock data.

Fine-tunes Qwen1.5-0.5B on clean AAPL seed data or clean retain buffer.
"""

import logging
import os
import sys
import time

import torch
from transformers import HfArgumentParser, Trainer, TrainingArguments, set_seed

from stocksense.utils.model_utils import load_model_and_tokenizer
from stocksense.data.buffer_tokenizer import tokenize_buffer

logger = logging.getLogger(__name__)


def run_finetune(
    model_path: str,
    train_data_path: str,
    output_dir: str,
    learning_rate: float = 5e-6,
    epochs: int = 1,
    batch_size: int = 1,
    gradient_accumulation: int = 8,
    max_length: int = 256,
    seed: int = 42,
    fp16: bool = True,
    max_steps: int = -1,
) -> str:
    """Run fine-tuning on stock data.

    Args:
        model_path: Path to base or previously unlearned model.
        train_data_path: Path to JSONL or .pt tokenized dataset.
        output_dir: Where to save the fine-tuned model.
        learning_rate: Learning rate (default 5e-6, lower than chatbot).
        epochs: Number of training epochs.
        batch_size: Per-device batch size.
        gradient_accumulation: Gradient accumulation steps.
        max_length: Max sequence length.
        seed: Random seed.
        fp16: Use mixed precision.

    Returns:
        Path to the saved model directory.
    """
    set_seed(seed)

    logger.info(f"Loading model from {model_path}")
    model, tokenizer = load_model_and_tokenizer(model_path)

    # Load or tokenize dataset
    if train_data_path.endswith(".pt"):
        train_dataset = torch.load(train_data_path, weights_only=False)
    elif train_data_path.endswith(".jsonl"):
        train_dataset = tokenize_buffer(train_data_path, tokenizer, max_length)
    else:
        raise ValueError(f"Unsupported data format: {train_data_path}")

    logger.info(f"Training on {len(train_dataset)} samples")

    if len(train_dataset) == 0:
        logger.warning("Finetune dataset is empty. Skipping training.")
        os.makedirs(output_dir, exist_ok=True)
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
        # Free GPU memory
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return output_dir

    training_args = TrainingArguments(
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
        save_strategy="no",
        logging_steps=10,
        report_to="none",
        seed=seed,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
    )

    logger.info("Starting fine-tuning...")
    t0 = time.time()
    result = trainer.train()
    elapsed = time.time() - t0
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    logger.info(f"Fine-tuning done in {int(h)}h {int(m)}m {s:.1f}s")

    os.makedirs(output_dir, exist_ok=True)
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"Model saved to {output_dir}")

    # Free GPU memory
    del model, trainer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    logger.info("GPU memory freed after fine-tuning")

    return output_dir


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", default="./models/Qwen1.5-0.5B")
    parser.add_argument("--train_data", required=True)
    parser.add_argument("--output_dir", default="./output/stock/finetune")
    parser.add_argument("--lr", type=float, default=5e-6)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--config", help="JSON config file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_finetune(
        model_path=args.model_path,
        train_data_path=args.train_data,
        output_dir=args.output_dir,
        learning_rate=args.lr,
        epochs=args.epochs,
    )
