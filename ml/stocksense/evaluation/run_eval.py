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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--forget_data", required=True)
    parser.add_argument("--retain_data", required=True)
    parser.add_argument("--output_dir", default="./output/stock/eval")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    evaluate_model(args.model_path, args.forget_data, args.retain_data, args.output_dir)
