"""
metrics.py — compute_metrics and preprocess_logits helpers for evaluation.

Adapted from llm_unlearn/utils/utils.py.
"""

import torch
import numpy as np


def preprocess_logits_for_metrics(logits, labels):
    """Preprocess logits for metric computation — argmax prediction."""
    if isinstance(logits, tuple):
        logits = logits[0]
    return logits.argmax(dim=-1)


def compute_metrics(eval_preds):
    """Compute token-level accuracy metric."""
    try:
        import evaluate
        metric = evaluate.load("accuracy")
    except ImportError:
        raise ImportError("Install 'evaluate' package: pip install evaluate")

    preds, labels = eval_preds
    labels = labels[:, 1:].reshape(-1)
    preds = preds[:, :-1].reshape(-1)
    return metric.compute(predictions=preds, references=labels)


def compute_perplexity_and_accuracy(eval_preds):
    """Compute perplexity and accuracy from evaluation predictions.

    Used by run_eval.py for forget/retain PPL computation.
    """
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
    acc = (sum(accs) / len(accs) * 100).item() if accs else 0.0
    return {"ppl": ppl, "acc": acc}
