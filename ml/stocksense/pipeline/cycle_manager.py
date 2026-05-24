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
    mae_validation: float = float("inf")
    directional_acc: float = 0.0
    mia_auc: float = 0.5


def passes_gates(new: Metrics, prior: Metrics) -> Tuple[bool, str]:
    """Check deployment gates.

    Gates:
    1. forget_ppl improved by ≥10% (model forgot poisoned patterns)
    2. retain_ppl not degraded >10% (clean knowledge preserved)
    3. MAE not degraded >5% (prediction quality)
    4. Directional accuracy > 0.52 (beats coin-flip)
    5. MIA AUC warning only (secondary for stocks)
    """
    # Gate 1: Forget PPL should increase (model forgetting poison)
    if prior.forget_ppl > 0 and new.forget_ppl <= prior.forget_ppl * 1.10:
        return False, "forget_ppl not improved by 10%"

    # Gate 2: Retain PPL should not degrade
    if prior.retain_ppl > 0 and new.retain_ppl > prior.retain_ppl * 1.10:
        return False, "retain_ppl degraded >10%"

    # Gate 3: MAE should not degrade
    if (
        prior.mae_validation < float("inf")
        and new.mae_validation > prior.mae_validation * 1.05
    ):
        return False, "MAE degraded >5%"

    # Gate 4: Directional accuracy above coin-flip
    if new.directional_acc < 0.52:
        return False, "directional accuracy below coin-flip"

    # Gate 5: MIA is warning-only for stocks
    # (no hard gate — logged but doesn't block deployment)

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
    ) -> dict:
        """Run a full super-learning cycle.

        Args:
            method: Unlearning method to use.
            learning_rate: Learning rate for unlearning.
            epochs: Number of training epochs.
            cycle_num: Override cycle number (auto-detects if None).
            callback: Optional callback(step, pct, data) for progress.

        Returns:
            Dict with cycle results.
        """
        from stocksense.pipeline.model_registry import ModelRegistry
        from stocksense.data.buffer_router import (
            count_buffer,
            archive_buffers,
        )

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
        )

        # --- Step 4: Evaluate (PPL + MAE + Directional Accuracy) ---
        _notify(callback, "evaluating", 75)
        new_metrics = Metrics()

        # 4a. PPL evaluation — tokenize from JSONL on-the-fly
        try:
            from stocksense.evaluation.run_eval import evaluate_from_jsonl
            eval_results = evaluate_from_jsonl(
                model_path=superlearn_output,
                forget_jsonl=forget_path,
                retain_jsonl=retain_path,
                max_length=256,
            )
            new_metrics.forget_ppl = eval_results.get("forget_ppl", 0.0)
            new_metrics.retain_ppl = eval_results.get("retain_ppl", 0.0)
            logger.info(f"PPL eval: forget={new_metrics.forget_ppl:.2f} retain={new_metrics.retain_ppl:.2f}")
        except Exception as e:
            logger.warning(f"PPL evaluation failed (falling back to .pt): {e}")
            # Fallback: try pre-tokenized .pt files
            try:
                from stocksense.evaluation.run_eval import evaluate_model
                tokenized_base = os.environ.get("TOKENIZED_BASE", "./tokenized_dataset")
                forget_tok = os.path.join(tokenized_base, "stock", "forget", "normal", "tokenized_dataset.pt")
                retain_tok = os.path.join(tokenized_base, "stock", "retain", "normal", "tokenized_dataset.pt")
                if os.path.exists(forget_tok) and os.path.exists(retain_tok):
                    eval_results = evaluate_model(
                        superlearn_output, forget_tok, retain_tok,
                        os.path.join(cycle_dir, "eval"),
                    )
                    new_metrics.forget_ppl = eval_results.get("forget", {}).get("ppl", 0)
                    new_metrics.retain_ppl = eval_results.get("retain", {}).get("ppl", 0)
            except Exception as e2:
                logger.warning(f"Fallback .pt evaluation also failed: {e2}")

        # 4b. MAE + Directional accuracy evaluation
        try:
            from stocksense.evaluation.prediction_eval import evaluate_predictions
            mae_results = evaluate_predictions(
                model_path=superlearn_output,
                data_base=self.data_base,
                ticker=os.environ.get("TICKER", "AAPL"),
            )
            new_metrics.mae_validation = mae_results.get("mae", float("inf"))
            new_metrics.directional_acc = mae_results.get("directional_acc", 0.0)
            logger.info(f"MAE={new_metrics.mae_validation:.4f} DirAcc={new_metrics.directional_acc:.2%}")
        except Exception as e:
            logger.warning(f"MAE evaluation failed: {e}")

        # --- Step 5: Gate check ---
        _notify(callback, "gate_check", 90)
        prior_metrics = self._load_prior_metrics(cycle_num - 1)
        deployed, gate_failure = passes_gates(new_metrics, prior_metrics)

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
                "forget_ppl": new_metrics.forget_ppl,
                "retain_ppl": new_metrics.retain_ppl,
                "mae_validation": new_metrics.mae_validation,
                "directional_acc": new_metrics.directional_acc,
                "mia_auc": new_metrics.mia_auc,
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
            "forget_ppl": new_metrics.forget_ppl,
            "retain_ppl": new_metrics.retain_ppl,
            "mae_validation": new_metrics.mae_validation,
            "directional_acc": new_metrics.directional_acc,
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
                    mae_validation=entry.get("mae_validation", float("inf")),
                    directional_acc=entry.get("directional_acc", 0),
                    mia_auc=entry.get("mia_auc", 0.5),
                )
        return Metrics()


def _notify(callback, step, pct):
    if callback:
        callback(step, pct, {})
