"""
buffer_tokenizer.py — JSONL buffers → tokenized PT files.

Tokenizes text windows from JSONL buffer files into HuggingFace datasets
ready for unlearning training.
"""

import json
import logging
import os
import copy
from typing import Optional

import torch
from datasets import Dataset
from transformers import AutoTokenizer, BatchEncoding

logger = logging.getLogger(__name__)


def load_jsonl_texts(jsonl_path: str) -> list:
    """Load text entries from a JSONL file."""
    texts = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entry = json.loads(line)
                texts.append(entry.get("text", ""))
    return texts


def tokenize_texts(
    texts: list,
    tokenizer,
    max_length: int = 256,
) -> Dataset:
    """Tokenize a list of text strings into a HuggingFace Dataset."""
    dataset = Dataset.from_dict({"text": texts})

    def tokenize_fn(examples):
        output = tokenizer(examples["text"])
        result = {"input_ids": [], "attention_mask": []}
        for i in range(len(output["input_ids"])):
            ids = output["input_ids"][i]
            mask = output["attention_mask"][i]
            n_chunks = len(ids) // max_length + int(len(ids) % max_length != 0)
            for j in range(n_chunks):
                s = j * max_length
                e = s + max_length
                chunk_ids = ids[s:e]
                chunk_mask = mask[s:e]
                if len(chunk_ids) < 5:
                    continue
                pad_len = max_length - len(chunk_ids)
                chunk_ids += [tokenizer.pad_token_id] * pad_len
                chunk_mask += [0] * pad_len
                result["input_ids"].append(chunk_ids)
                result["attention_mask"].append(chunk_mask)
        return result

    tokenized = dataset.map(
        tokenize_fn, batched=True, remove_columns=["text"],
        desc="Tokenizing buffer", load_from_cache_file=False,
    )
    # Add labels (copy of input_ids with padding masked to -100)
    def add_labels(examples):
        labels = copy.deepcopy(examples["input_ids"])
        for i, seq in enumerate(labels):
            labels[i] = [-100 if t == tokenizer.pad_token_id else t for t in seq]
        examples["labels"] = labels
        return examples

    tokenized = tokenized.map(add_labels, batched=True, desc="Adding labels")
    return tokenized


def tokenize_buffer(
    jsonl_path: str,
    tokenizer,
    max_length: int = 256,
    save_path: Optional[str] = None,
) -> Dataset:
    """Tokenize a JSONL buffer file into a dataset.

    Args:
        jsonl_path: Path to JSONL buffer file.
        tokenizer: HuggingFace tokenizer.
        max_length: Maximum sequence length.
        save_path: Optional path to save the tokenized dataset.

    Returns:
        Tokenized HuggingFace Dataset.
    """
    texts = load_jsonl_texts(jsonl_path)
    logger.info(f"Loaded {len(texts)} texts from {jsonl_path}")
    dataset = tokenize_texts(texts, tokenizer, max_length)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        torch.save(dataset, save_path)
        logger.info(f"Saved tokenized dataset to {save_path}")
    return dataset


def prepare_ad_dataset(
    forget_jsonl: str,
    retain_jsonl: str,
    tokenizer,
    max_length: int = 256,
    positive_ratio: int = 3,
    positive_factor: float = 1.0,
    save_path: Optional[str] = None,
):
    """Prepare an AdvSupervisedDataset for Ascent+Descent training.

    Interleaves forget (factor=-1) and retain (factor=positive_factor) samples.
    """
    from .adv_dataset import AdvSupervisedDataset

    class DataArgs:
        def __init__(self, pr, pf):
            self.positive_ratio = pr
            self.positive_factor = pf

    forget_ds = tokenize_buffer(forget_jsonl, tokenizer, max_length)
    retain_ds = tokenize_buffer(retain_jsonl, tokenizer, max_length)

    data_args = DataArgs(positive_ratio, positive_factor)
    ad_dataset = AdvSupervisedDataset(forget_ds, retain_ds, data_args)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        torch.save(ad_dataset, save_path)
        logger.info(f"Saved AD dataset to {save_path}")
    return ad_dataset
