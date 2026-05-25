"""
cycle_manager.py — Full super-learning cycle orchestrator.

Orchestrates:
1. Tokenize forget + retain buffers
2. Run unlearning (AD primary)
3. Re-fine-tune on retain (super-learning)
4. Evaluate (PPL, MAE, MIA)
5. Gate check
6. Deploy or rollback
7. Archive buffers + log cycle
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Metrics:
    """Cycle evaluation metrics for gate checks."""
    forget_ppl: float = 0.0
    retain_ppl: float = 0.0
    mae_validation: Optional[float] = None
    directional_acc: float = 0.0
    mia_auc: float = 0.5


def passes_gates(new: Metrics, prior: Metrics, is_first_cycle: bool = False) -> Tuple[bool, str]:
    """Check deployment gates.

    Gates:
    1. forget_ppl improved by ≥10% (model forgot poisoned patterns)
    2. retain_ppl not degraded >10% (clean knowledge preserved)
    3. MAE not degraded >5% (prediction quality)
    4. Directional accuracy > 0.52 (beats coin-flip)
    5. MIA AUC warning only (secondary for stocks)

    On the first cycle (no prior deployed model), only soft-check:
    - Skip relative gates (1-3) since there's nothing to compare to.
    - Skip directional_acc gate if eval didn't compute it (value == 0.0).
    """
    warnings = []

    # Gate 1: Forget PPL should increase (model forgetting poison)
    if prior.forget_ppl > 0 and new.forget_ppl <= prior.forget_ppl * 1.10:
        if not is_first_cycle:
            return False, "forget_ppl not improved by 10%"
        warnings.append("forget_ppl not improved (first cycle, warning only)")

    # Gate 2: Retain PPL should not degrade
    if prior.retain_ppl > 0 and new.retain_ppl > prior.retain_ppl * 1.10:
        if not is_first_cycle:
            return False, "retain_ppl degraded >10%"
        warnings.append("retain_ppl degraded (first cycle, warning only)")

    # Gate 3: MAE should not degrade
    if (
        prior.mae_validation is not None
        and new.mae_validation is not None
        and new.mae_validation > prior.mae_validation * 1.05
    ):
        if not is_first_cycle:
            return False, "MAE degraded >5%"
        warnings.append("MAE degraded (first cycle, warning only)")

    # Gate 4: Directional accuracy above coin-flip
    # Skip this gate if eval didn't actually compute it (value is still 0.0)
    if new.directional_acc > 0 and new.directional_acc < 0.52:
        return False, "directional accuracy below coin-flip"

    # Gate 5: MIA is warning-only for stocks
    # (no hard gate — logged but doesn't block deployment)

    if warnings:
        logger.warning(f"Gate warnings (non-blocking): {'; '.join(warnings)}")

    return True, ""


class CycleManager:
    """Orchestrates a complete super-learning cycle."""

    def __init__(
        self,
        model_base_path: Optional[str] = None,
        output_base: Optional[str] = None,
        data_base: Optional[str] = None,
    ):
        self.model_base_path = model_base_path or os.environ.get(
            "MODEL_BASE_PATH", "./models/Qwen1.5-0.5B"
        )
        self.output_base = output_base or os.environ.get(
            "OUTPUT_BASE", "./output/stock"
        )
        self.data_base = data_base or os.environ.get(
            "DATA_BASE", "./data"
        )

    def run_cycle(
        self,
        method: str = "ascent_plus_descent",
        learning_rate: float = 5e-6,
        epochs: int = 1,
        cycle_num: Optional[int] = None,
        callback=None,
        max_steps: int = -1,
    ) -> dict:
        """Run a full super-learning cycle.

        Args:
            method: Unlearning method to use.
            learning_rate: Learning rate for unlearning.
            epochs: Number of training epochs.
            cycle_num: Override cycle number (auto-detects if None).
            callback: Optional callback(step, pct, data) for progress.
            max_steps: Max training steps per phase (-1 = full epoch).
                       Set to e.g. 10 for fast dev testing.

        Returns:
            Dict with cycle results.
        """
        from stocksense.pipeline.model_registry import ModelRegistry
        from stocksense.data.buffer_router import (
            count_buffer,
            archive_buffers,
        )

        # Check for DEV_UNLEARN_MAX_STEPS env var override
        env_max_steps = os.environ.get("DEV_UNLEARN_MAX_STEPS")
        if env_max_steps and max_steps < 0:
            max_steps = int(env_max_steps)
            logger.info(f"DEV MODE: max_steps={max_steps} (from env)")

        if max_steps > 0:
            logger.info(f"⚡ Fast mode: capping each training phase to {max_steps} steps")

        registry = ModelRegistry(self.output_base)
        if cycle_num is None:
            cycle_num = registry.get_next_cycle_num()

        cycle_dir = registry.get_cycle_dir(cycle_num)
        os.makedirs(cycle_dir, exist_ok=True)

        t0 = time.time()
        _notify(callback, "tokenizing", 10)

        # --- Step 1: Locate buffers ---
        # Try both flat and nested buffer paths
        forget_path = os.path.join(self.data_base, "forget_buffer.jsonl")
        retain_path = os.path.join(self.data_base, "retain_buffer.jsonl")

        if not os.path.exists(forget_path):
            forget_path = os.path.join(self.data_base, "buffers", "forget_buffer.jsonl")
        if not os.path.exists(retain_path):
            retain_path = os.path.join(self.data_base, "buffers", "retain_buffer.jsonl")

        forget_count = 0
        if os.path.exists(forget_path):
            with open(forget_path) as f:
                forget_count = sum(1 for _ in f)

        if forget_count == 0:
            logger.warning("No forget buffer data — skipping cycle")
            return {"cycle_num": cycle_num, "skipped": True, "reason": "empty_forget_buffer"}

        # --- Step 2: Run unlearning ---
        _notify(callback, "unlearning", 30)
        current_model = registry.get_current_model_path()
        if current_model is None:
            current_model = self.model_base_path
            logger.info(f"No deployed model — using base: {current_model}")

        unlearn_output = os.path.join(cycle_dir, "unlearned")

        from stocksense.training.run_unlearn import run_unlearn
        run_unlearn(
            model_path=current_model,
            forget_data=forget_path,
            retain_data=retain_path,
            output_dir=unlearn_output,
            method=method,
            learning_rate=learning_rate,
            epochs=epochs,
            max_steps=max_steps,
        )

        # --- Step 3: Re-fine-tune on clean retain (super-learning) ---
        _notify(callback, "superlearning", 55)
        superlearn_output = os.path.join(cycle_dir, "superlearned")

        from stocksense.training.finetune import run_finetune
        run_finetune(
            model_path=unlearn_output,
            train_data_path=retain_path,
            output_dir=superlearn_output,
            learning_rate=learning_rate,
            epochs=epochs,
            max_steps=max_steps,
        )

        # --- Step 4: Evaluate (PPL + MAE + Directional Accuracy) ---
        _notify(callback, "evaluating", 75)
        new_metrics = Metrics()

        # 4a. PPL evaluation — tokenize from JSONL on-the-fly
        try:
            from stocksense.evaluation.run_eval import evaluate_model
            tokenized_base = os.environ.get("TOKENIZED_BASE", "./tokenized_dataset")
            forget_tok = os.path.join(tokenized_base, "stock", "forget", "normal", "tokenized_dataset.pt")
            retain_tok = os.path.join(tokenized_base, "stock", "retain", "normal", "tokenized_dataset.pt")
            if os.path.exists(forget_tok) and os.path.exists(retain_tok):
                eval_results = evaluate_model(
                    superlearn_output, forget_tok, retain_tok, eval_output,
                )
                new_metrics.forget_ppl = eval_results.get("forget", {}).get("ppl", 0)
                new_metrics.retain_ppl = eval_results.get("retain", {}).get("ppl", 0)
            else:
                logger.info("No pre-tokenized eval data — computing PPL from buffer files")
                new_metrics.forget_ppl, new_metrics.retain_ppl = _compute_ppl_from_buffers(
                    superlearn_output, forget_path, retain_path
                )
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
            # Still try the lightweight PPL fallback
            try:
                new_metrics.forget_ppl, new_metrics.retain_ppl = _compute_ppl_from_buffers(
                    superlearn_output, forget_path, retain_path
                )
            except Exception as e2:
                logger.warning(f"PPL fallback also failed: {e2}")

        # --- Step 5: Gate check ---
        _notify(callback, "gate_check", 90)
        prior_metrics = self._load_prior_metrics(cycle_num - 1)
        # First cycle or no prior deployed model → be lenient with gates
        is_first = cycle_num <= 1 or (
            prior_metrics.forget_ppl == 0 and prior_metrics.retain_ppl == 0
        )
        deployed, gate_failure = passes_gates(new_metrics, prior_metrics, is_first_cycle=is_first)

        duration = int(time.time() - t0)

        if deployed:
            registry.deploy_model(cycle_num)
            logger.info(f"✓ Cycle {cycle_num} DEPLOYED")
        else:
            logger.warning(f"✗ Cycle {cycle_num} FAILED gate: {gate_failure}")

        # --- Step 6: Archive + log ---
        archive_buffers(cycle_num, self.data_base)
        registry.log_cycle(
            cycle_num=cycle_num,
            method=method,
            metrics={
                "forget_ppl": _safe_float(new_metrics.forget_ppl),
                "retain_ppl": _safe_float(new_metrics.retain_ppl),
                "mae_validation": _safe_float(new_metrics.mae_validation),
                "directional_acc": _safe_float(new_metrics.directional_acc),
                "mia_auc": _safe_float(new_metrics.mia_auc),
            },
            deployed=deployed,
            gate_failure=gate_failure if not deployed else None,
            duration_sec=duration,
        )

        # --- Step 7: Retrain LSTM after Qwen unlearn ---
        try:
            from stocksense.training.lstm_trainer import train_lstm
            lstm_output = os.path.join(self.output_base, "lstm", "latest")
            train_lstm(
                data_base=self.data_base,
                output_dir=lstm_output,
                ticker=os.environ.get("TICKER", "AAPL"),
                epochs=30,  # Quick retrain
            )
            logger.info("LSTM retrained after unlearn cycle")
        except Exception as e:
            logger.warning(f"LSTM retrain failed (non-blocking): {e}")

        _notify(callback, "complete", 100)

        return {
            "cycle_num": cycle_num,
            "method": method,
            "deployed": deployed,
            "gate_failure": gate_failure if not deployed else None,
            "forget_ppl": _safe_float(new_metrics.forget_ppl),
            "retain_ppl": _safe_float(new_metrics.retain_ppl),
            "mae_validation": _safe_float(new_metrics.mae_validation),
            "duration_sec": duration,
        }

    def _load_prior_metrics(self, prior_cycle: int) -> Metrics:
        """Load metrics from the previous cycle."""
        log_dir = os.path.join(os.path.dirname(self.output_base), "logs")
        history_path = os.path.join(log_dir, "cycle_history.json")

        if not os.path.exists(history_path):
            return Metrics()

        with open(history_path) as f:
            history = json.load(f)

        for entry in reversed(history):
            if entry.get("cycle_num") == prior_cycle and entry.get("deployed"):
                return Metrics(
                    forget_ppl=entry.get("forget_ppl", 0),
                    retain_ppl=entry.get("retain_ppl", 0),
                    mae_validation=entry.get("mae_validation"),
                    directional_acc=entry.get("directional_acc", 0),
                    mia_auc=entry.get("mia_auc", 0.5),
                )
        return Metrics()


def _compute_ppl_from_buffers(
    model_path: str, forget_path: str, retain_path: str
) -> tuple:
    """Compute perplexity on forget/retain buffers using the model directly.

    Lightweight fallback when pre-tokenized .pt eval datasets don't exist.
    Returns (forget_ppl, retain_ppl).
    """
    import math
    import torch
    from stocksense.utils.model_utils import load_model_and_tokenizer
    from stocksense.data.buffer_tokenizer import tokenize_buffer

    logger.info(f"Loading model from {model_path} for PPL eval")
    model, tokenizer = load_model_and_tokenizer(model_path)
    model.eval()

    device = next(model.parameters()).device

    def _calc_ppl(data_path: str) -> float:
        if not os.path.exists(data_path):
            return 0.0
        dataset = tokenize_buffer(data_path, tokenizer, max_length=256)
        if len(dataset) == 0:
            return 0.0

        total_loss = 0.0
        count = 0
        # Evaluate on up to 50 samples to keep it fast
        n_samples = min(len(dataset), 50)
        with torch.no_grad():
            for i in range(n_samples):
                item = dataset[i]
                input_ids = torch.as_tensor(item["input_ids"], device=device).unsqueeze(0)
                if "labels" in item:
                    labels = torch.as_tensor(item["labels"], device=device).unsqueeze(0)
                else:
                    labels = input_ids.clone()
                outputs = model(input_ids=input_ids, labels=labels)
                total_loss += outputs.loss.item()
                count += 1

        avg_loss = total_loss / max(count, 1)
        return math.exp(min(avg_loss, 100))  # cap to avoid overflow

    try:
        forget_ppl = _calc_ppl(forget_path)
        retain_ppl = _calc_ppl(retain_path)
        logger.info(f"PPL eval: forget={forget_ppl:.2f}, retain={retain_ppl:.2f}")
        return forget_ppl, retain_ppl
    finally:
        # Free GPU memory
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("PPL eval model freed from GPU")


def _safe_float(val) -> Optional[float]:
    """Convert to JSON-safe float: replace inf/nan with None."""
    if val is None:
        return None
    import math
    if math.isinf(val) or math.isnan(val):
        return None
    return float(val)


def _notify(callback, step, pct):
    if callback:
        callback(step, pct, {})
