"""
run_eval.py — PPL + token accuracy evaluation on forget/retain sets.

Evaluates:
- forget set: perplexity + accuracy (want HIGH ppl = model forgot)
- retain set: perplexity + accuracy (want LOW ppl = model retained)

Adapted from llm_unlearn/run_eval.py for stock domain.
"""

import json
import logging
import math
import os
import sys

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    HfArgumentParser,
    Trainer,
    TrainingArguments,
    set_seed,
)

logger = logging.getLogger(__name__)


def _supports_tf32():
    if not torch.cuda.is_available():
        return False
    return torch.cuda.get_device_capability(0)[0] >= 8


def evaluate_model(
    model_path: str,
    forget_data_path: str,
    retain_data_path: str,
    output_dir: str,
    seed: int = 42,
) -> dict:
    """Evaluate a model on forget and retain datasets.

    Returns:
        Dict with forget_ppl, forget_acc, retain_ppl, retain_acc.
    """
    set_seed(seed)

    torch_dtype = torch.bfloat16 if _supports_tf32() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_path, torch_dtype=torch_dtype, trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, padding_side="right", trust_remote_code=True,
    )
    if len(tokenizer) > model.get_input_embeddings().weight.shape[0]:
        model.resize_token_embeddings(len(tokenizer))

    # Load datasets
    forget_ds = torch.load(forget_data_path, weights_only=False)
    retain_ds = torch.load(retain_data_path, weights_only=False)

    def preprocess_logits(logits, labels):
        if isinstance(logits, tuple):
            logits = logits[0]
        labels_c = labels.clone()[:, 1:]
        pad_mask = labels_c != -100
        log_probs = torch.log_softmax(logits, dim=-1)[:, :-1]
        idx = labels_c.unsqueeze(-1).clamp(min=0)
        sel_lp = log_probs.gather(2, idx) * pad_mask.unsqueeze(-1)
        pred = logits.argmax(dim=-1)[:, :-1]
        return torch.cat((sel_lp.squeeze(-1), pred), 1)

    def compute_metrics(eval_preds):
        preds, labels = eval_preds
        preds = torch.as_tensor(preds)
        labels = torch.as_tensor(labels)
        half = preds.shape[1] // 2
        sel_lp = preds[:, :half]
        predicts = preds[:, half:]
        labels_c = labels.clone()[:, 1:]
        mask = labels_c != -100
        pred_mask = predicts == labels_c

        ppls, accs = [], []
        for lp, m, pm in zip(sel_lp, mask, pred_mask):
            lp_nonpad = lp[m]
            if lp_nonpad.numel() == 0:
                continue
            avg_lp = lp_nonpad.mean()
            ppls.append(avg_lp)
            accs.append(pm[m].float().mean())

        if not ppls:
            return {"ppl": float("inf"), "acc": 0.0}
        avg_lp = torch.stack(ppls).mean()
        ppl = torch.exp(-avg_lp).item()
        acc = (sum(accs) / len(accs) * 100).item()
        return {"ppl": ppl, "acc": acc}

    training_args = TrainingArguments(
        output_dir=output_dir, do_eval=True, per_device_eval_batch_size=4,
        report_to="none",
    )
    trainer = Trainer(
        model=model, args=training_args,
        compute_metrics=compute_metrics,
        preprocess_logits_for_metrics=preprocess_logits,
    )

    os.makedirs(output_dir, exist_ok=True)
    summary = {}

    for key, ds in [("forget", forget_ds), ("retain", retain_ds)]:
        metrics = trainer.evaluate(ds)
        try:
            metrics["perplexity"] = math.exp(metrics["eval_loss"])
        except (OverflowError, KeyError):
            metrics["perplexity"] = float("inf")
        summary[key] = {
            "ppl": metrics.get("eval_ppl", metrics.get("perplexity", 0)),
            "acc": metrics.get("eval_acc", 0),
            "loss": metrics.get("eval_loss", 0),
        }
        logger.info(f"[{key}] ppl={summary[key]['ppl']:.2f} acc={summary[key]['acc']:.2f}")

    # Save results
    results_path = os.path.join(output_dir, "eval_results.json")
    with open(results_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Evaluation results saved to {results_path}")

    return summary


def evaluate_from_jsonl(
    model_path: str,
    forget_jsonl: str,
    retain_jsonl: str,
    max_length: int = 256,
    seed: int = 42,
) -> dict:
    """Evaluate model by tokenizing JSONL buffers on-the-fly.

    This is the primary evaluation path — no pre-tokenized .pt files needed.

    Args:
        model_path: Path to model to evaluate.
        forget_jsonl: Path to forget_buffer.jsonl.
        retain_jsonl: Path to retain_buffer.jsonl.
        max_length: Max token sequence length.
        seed: Random seed.

    Returns:
        Dict with forget_ppl and retain_ppl.
    """
    set_seed(seed)

    from stocksense.data.buffer_tokenizer import tokenize_buffer
    from stocksense.utils.model_utils import load_model_and_tokenizer

    model, tokenizer = load_model_and_tokenizer(model_path)
    model.eval()

    results = {}
    try:
        for key, jsonl_path in [("forget", forget_jsonl), ("retain", retain_jsonl)]:
            if not os.path.exists(jsonl_path):
                logger.warning(f"{key} JSONL not found: {jsonl_path}")
                results[f"{key}_ppl"] = 0.0
                continue

            # Count lines
            with open(jsonl_path) as f:
                line_count = sum(1 for _ in f)
            if line_count == 0:
                results[f"{key}_ppl"] = 0.0
                continue

            try:
                dataset = tokenize_buffer(jsonl_path, tokenizer, max_length)
                ppl, acc = _compute_ppl(model, dataset)
                results[f"{key}_ppl"] = ppl
                results[f"{key}_acc"] = acc
                logger.info(f"[{key}] ppl={ppl:.2f}, acc={acc:.2f}% (from {line_count} JSONL entries)")
            except Exception as e:
                logger.warning(f"Failed to evaluate {key}: {e}")
                results[f"{key}_ppl"] = 0.0
                results[f"{key}_acc"] = 0.0

        return results
    finally:
        del model
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _compute_ppl(model, dataset) -> tuple:
    """Compute perplexity and accuracy on a tokenized dataset."""
    from torch.utils.data import DataLoader

    loader = DataLoader(dataset, batch_size=4, shuffle=False)
    total_loss = 0.0
    total_tokens = 0
    total_correct = 0

    model.eval()
    device = next(model.parameters()).device

    with torch.no_grad():
        for batch in loader:
            # Handle both tensor and list inputs from DataLoader
            if isinstance(batch["input_ids"], list):
                if len(batch["input_ids"]) > 0 and isinstance(batch["input_ids"][0], torch.Tensor):
                    input_ids = torch.stack(batch["input_ids"], dim=1).to(device)
                else:
                    input_ids = torch.as_tensor(batch["input_ids"], device=device)
            else:
                input_ids = batch["input_ids"].to(device)
                
            if isinstance(batch["attention_mask"], list):
                if len(batch["attention_mask"]) > 0 and isinstance(batch["attention_mask"][0], torch.Tensor):
                    attention_mask = torch.stack(batch["attention_mask"], dim=1).to(device)
                else:
                    attention_mask = torch.as_tensor(batch["attention_mask"], device=device)
            else:
                attention_mask = batch["attention_mask"].to(device)
                
            labels = input_ids.clone()

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
            )
            
            logits = outputs.logits
            shift_logits = logits[..., :-1, :].contiguous()
            shift_labels = labels[..., 1:].contiguous()
            shift_mask = attention_mask[..., 1:].contiguous()
            
            preds = shift_logits.argmax(dim=-1)
            correct = (preds == shift_labels) & shift_mask.bool()
            total_correct += correct.sum().item()
            
            n_tokens = shift_mask.sum().item()
            if n_tokens > 0:
                total_loss += outputs.loss.item() * n_tokens
                total_tokens += n_tokens

    if total_tokens == 0:
        return float("inf"), 0.0

    avg_loss = total_loss / total_tokens
    acc = (total_correct / total_tokens) * 100.0
    try:
        return math.exp(avg_loss), acc
    except OverflowError:
        return float("inf"), acc


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--forget_data", required=True)
    parser.add_argument("--retain_data", required=True)
    parser.add_argument("--output_dir", default="./output/stock/eval")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    
    if args.forget_data.endswith('.jsonl') or args.retain_data.endswith('.jsonl'):
        res = evaluate_from_jsonl(args.model_path, args.forget_data, args.retain_data)
        
        # Save results similar to evaluate_model
        os.makedirs(args.output_dir, exist_ok=True)
        results_path = os.path.join(args.output_dir, "eval_results.json")
        with open(results_path, "w") as f:
            json.dump(res, f, indent=2)
        logger.info(f"Evaluation results saved to {results_path}")
    else:
        evaluate_model(args.model_path, args.forget_data, args.retain_data, args.output_dir)
