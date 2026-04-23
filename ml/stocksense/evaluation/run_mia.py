"""
run_mia.py — Membership Inference Attack evaluation for stock domain.

Uses Min-K% Prob attack to measure if poisoned windows can be distinguished
from clean windows based on model confidence.

Adapted from llm_unlearn/run_mia.py.
"""

import json
import logging
import os
import random
from collections import defaultdict
from typing import Dict

import numpy as np
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
    set_seed,
)

logger = logging.getLogger(__name__)


def _supports_tf32():
    if not torch.cuda.is_available():
        return False
    return torch.cuda.get_device_capability(0)[0] >= 8


def fig_fpr_tpr(all_output, output_dir):
    """Generate ROC curves and compute AUC for MIA evaluation."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import auc, roc_curve
    except ImportError:
        logger.warning("matplotlib/sklearn not available for MIA plots")
        # Still write AUC text if possible
        return

    answers = []
    metric2predictions = defaultdict(list)
    for ex in all_output:
        answers.append(ex["label"])
        for metric in ex["pred"].keys():
            if ("raw" in metric) and ("clf" not in metric):
                continue
            metric2predictions[metric].append(ex["pred"][metric])

    plt.figure(figsize=(4, 3))
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/auc.txt", "w") as f:
        for metric, predictions in metric2predictions.items():
            fpr, tpr, _ = roc_curve(
                np.array(answers, dtype=bool), -np.array(predictions)
            )
            auc_val = auc(fpr, tpr)
            if auc_val < 0.5:
                auc_val = 1 - auc_val
            acc = np.max(1 - (fpr + (1 - tpr)) / 2)
            low = tpr[np.where(fpr < 0.05)[0][-1]] if len(np.where(fpr < 0.05)[0]) > 0 else 0.0
            f.write(f"{metric}   AUC {auc_val:.4f}, Acc {acc:.4f}, TPR@5%FPR {low:.4f}\n")
            plt.plot(fpr, tpr, label=f"{metric} auc={auc_val:.3f}")
            logger.info(f"MIA {metric}: AUC={auc_val:.4f} Acc={acc:.4f}")

    plt.semilogx()
    plt.semilogy()
    plt.xlim(1e-5, 1)
    plt.ylim(1e-5, 1)
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.plot([0, 1], [0, 1], ls="--", color="gray")
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/auc.png")
    plt.close()


def run_mia(
    model_path: str,
    forget_data_path: str,
    retain_data_path: str,
    output_dir: str,
    seed: int = 42,
) -> dict:
    """Run Membership Inference Attack evaluation.

    Args:
        model_path: Path to the model to evaluate.
        forget_data_path: Forget (member) tokenized dataset path.
        retain_data_path: Retain (non-member) tokenized dataset path.
        output_dir: Where to save AUC results and plots.

    Returns:
        Dict with AUC scores per Min-K ratio.
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

    forget_ds = torch.load(forget_data_path, weights_only=False)
    retain_ds = torch.load(retain_data_path, weights_only=False)

    # Balance sizes
    n = min(len(forget_ds), len(retain_ds))
    if len(retain_ds) > n:
        retain_ds = retain_ds.select(range(n))
    if len(forget_ds) > n:
        forget_ds = forget_ds.select(range(n))

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
        half = preds.shape[1] // 2
        sel_lp = preds[:, :half]
        labels_c = labels.copy()[:, 1:]
        pad_mask = labels_c != -100

        result = {}
        for ratio in [0.3, 0.4, 0.5, 0.6, 1.0]:
            scores = []
            for lp, m in zip(sel_lp, pad_mask):
                lp_t = torch.tensor(lp)
                m_t = torch.tensor(m, dtype=torch.bool)
                nonpad_lp = lp_t[m_t]
                lp_copy = lp_t.clone()
                lp_copy[~m_t] = 100.0
                kv = max(1, int(ratio * nonpad_lp.numel()))
                topk = torch.topk(lp_copy, kv, largest=False)
                scores.append(topk.values.mean())
            result[f"min_{int(ratio * 100)}_value"] = torch.stack(scores)
        return result

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
    all_results = []

    for key, ds, mem_label in [
        ("forget", forget_ds, 1),
        ("retain", retain_ds, 0),
    ]:
        metrics = trainer.evaluate(ds)
        metrics_filtered = {
            k: v for k, v in metrics.items() if "min_" in k
        }
        if not metrics_filtered:
            continue

        lengths = [len(v) for v in metrics_filtered.values()]
        for i in range(lengths[0]):
            all_results.append({
                "label": mem_label,
                "pred": {k: float(v[i]) for k, v in metrics_filtered.items()},
            })

    random.seed(0)
    random.shuffle(all_results)
    fig_fpr_tpr(all_results, output_dir)

    logger.info(f"MIA results saved to {output_dir}/auc.txt")
    return {"output_dir": output_dir, "num_samples": len(all_results)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--forget_data", required=True)
    parser.add_argument("--retain_data", required=True)
    parser.add_argument("--output_dir", default="./output/stock/mia")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_mia(args.model_path, args.forget_data, args.retain_data, args.output_dir)
