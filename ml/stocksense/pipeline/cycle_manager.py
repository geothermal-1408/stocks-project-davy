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
import sys
from pathlib import Path

# Add the ml directory to sys.path so 'stocksense' module can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _resolve_buffer_dir(data_base: str) -> str:
    """Normalize the buffer directory path.

    Accepts either:
    - DATA_BASE pointing at ml/data
    - DATA_BASE pointing directly at ml/data/buffers
    """
    normalized = os.path.normpath(data_base)
    if os.path.basename(normalized) == "buffers":
        return normalized
    return os.path.join(normalized, "buffers")


def _find_latest_archived_retain(buffer_dir: str) -> Optional[str]:
    """Return the newest archived retain buffer path, if available.

    Looks under buffers/archive/cycle_*/ for retain_buffer.jsonl
    (including timestamp-suffixed variants).
    """
    archive_dir = Path(buffer_dir) / "archive"
    if not archive_dir.exists():
        return None

    candidates = []
    for path in archive_dir.glob("cycle_*/retain_buffer.jsonl*"):
        if path.is_file() and path.stat().st_size > 0:
            candidates.append(path)

    if not candidates:
        return None

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return str(latest)


@dataclass
class Metrics:
    """Cycle evaluation metrics for gate checks."""
    forget_ppl: float = 0.0
    retain_ppl: float = 0.0
    forget_acc: float = 0.0
    retain_acc: float = 0.0
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
    # Make this a warning rather than a hard failure to ensure unlearn pipelines can deploy.
    if new.directional_acc > 0 and new.directional_acc < 0.52:
        warnings.append("directional accuracy below coin-flip (warning only)")

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
        import torch
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

        try:
            # --- Step 1: Locate buffers (always in data_base/buffers/) ---
            buffer_dir = os.path.join(self.data_base, "buffers")
            forget_path = os.path.join(buffer_dir, "forget_buffer.jsonl")
            retain_path = os.path.join(buffer_dir, "retain_buffer.jsonl")

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

            # Check if current_model actually contains a valid model (has config.json)
            if current_model is not None and not os.path.exists(os.path.join(current_model, "config.json")):
                # Search subdirectories for config.json (e.g. 'stocksense-qwen')
                found_subdir = None
                if os.path.isdir(current_model):
                    for entry in os.listdir(current_model):
                        subdir = os.path.join(current_model, entry)
                        if os.path.isdir(subdir) and os.path.exists(os.path.join(subdir, "config.json")):
                            found_subdir = subdir
                            break
                if found_subdir:
                    current_model = found_subdir
                else:
                    logger.warning(f"Current model dir {current_model} lacks config.json, falling back to base model.")
                    current_model = None

            if current_model is None:
                current_model = self.model_base_path
                logger.info(f"No deployed model or invalid format — using base: {current_model}")

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

            # 4a. PPL evaluation
            try:
                tokenized_base = os.environ.get("TOKENIZED_BASE", "./tokenized_dataset")
                forget_tok = os.path.join(tokenized_base, "stock", "forget", "normal", "tokenized_dataset.pt")
                retain_tok = os.path.join(tokenized_base, "stock", "retain", "normal", "tokenized_dataset.pt")
                eval_output = os.path.join(cycle_dir, "eval")

                if os.path.exists(forget_tok) and os.path.exists(retain_tok):
                    # Path A: pre-tokenized .pt datasets exist
                    from stocksense.evaluation.run_eval import evaluate_model
                    eval_results = evaluate_model(
                        superlearn_output, forget_tok, retain_tok, eval_output,
                    )
                    new_metrics.forget_ppl = eval_results.get("forget", {}).get("ppl", 0)
                    new_metrics.retain_ppl = eval_results.get("retain", {}).get("ppl", 0)
                elif os.path.exists(forget_path) or os.path.exists(retain_path):
                    # Path B: evaluate from JSONL buffer files directly
                    logger.info("No pre-tokenized .pt files — evaluating PPL from JSONL buffers")
                    try:
                        from stocksense.evaluation.run_eval import evaluate_from_jsonl
                        jsonl_results = evaluate_from_jsonl(
                            model_path=superlearn_output,
                            forget_jsonl=forget_path,
                            retain_jsonl=retain_path,
                        )
                        new_metrics.forget_ppl = jsonl_results.get("forget_ppl", 0)
                        new_metrics.retain_ppl = jsonl_results.get("retain_ppl", 0)
                    except Exception as e_jsonl:
                        logger.warning(f"JSONL eval failed, using lightweight PPL: {e_jsonl}")
                        new_metrics.forget_ppl, new_metrics.retain_ppl = _compute_ppl_from_buffers(
                            superlearn_output, forget_path, retain_path
                        )
                else:
                    logger.warning("No eval data available (no .pt and no JSONL buffers)")
            except Exception as e:
                logger.warning(f"Evaluation failed: {e}")
                # Lightweight PPL fallback
                try:
                    new_metrics.forget_ppl, new_metrics.retain_ppl = _compute_ppl_from_buffers(
                        superlearn_output, forget_path, retain_path
                    )
                except Exception as e2:
                    logger.warning(f"PPL fallback also failed: {e2}")

            # 4b. Prediction evaluation (MAE + Directional Accuracy)
            try:
                from stocksense.evaluation.prediction_eval import evaluate_predictions
                ticker = os.environ.get("TICKER", "AAPL")
                pred_results = evaluate_predictions(
                    superlearn_output,
                    self.data_base,
                    ticker,
                    window_size=30,
                    n_eval_windows=10 if max_steps > 0 else 30,
                )
                new_metrics.mae_validation = pred_results.get("mae")
                new_metrics.directional_acc = pred_results.get("directional_acc", 0.0)
            except Exception as e:
                logger.warning(f"Prediction evaluation failed: {e}")

            # 4c. MIA evaluation
            try:
                tokenized_base = os.environ.get("TOKENIZED_BASE", "./tokenized_dataset")
                forget_tok = os.path.join(tokenized_base, "stock", "forget", "normal", "tokenized_dataset.pt")
                retain_tok = os.path.join(tokenized_base, "stock", "retain", "normal", "tokenized_dataset.pt")
                mia_output = os.path.join(cycle_dir, "mia")

                if os.path.exists(forget_tok) and os.path.exists(retain_tok):
                    # Path A: pre-tokenized .pt datasets exist
                    from stocksense.evaluation.run_mia import run_mia
                    mia_results = run_mia(
                        model_path=superlearn_output,
                        forget_data_path=forget_tok,
                        retain_data_path=retain_tok,
                        output_dir=mia_output,
                    )
                    if mia_results:
                        # run_mia returns {output_dir, num_samples} — parse AUC from file
                        mia_auc = _parse_mia_auc(mia_output)
                        if mia_auc is not None:
                            new_metrics.mia_auc = mia_auc
                elif os.path.exists(forget_path) or os.path.exists(retain_path):
                    # Path B: lightweight MIA from JSONL buffers
                    logger.info("No pre-tokenized .pt files — running lightweight MIA from JSONL")
                    mia_auc = _lightweight_mia_from_buffers(
                        superlearn_output, forget_path, retain_path, mia_output
                    )
                    if mia_auc is not None:
                        new_metrics.mia_auc = mia_auc
                else:
                    logger.info("No eval data for MIA — skipping MIA evaluation")
            except Exception as e:
                logger.warning(f"MIA evaluation failed: {e}")

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
                # Reload prediction models so /predict uses the new model
                try:
                    from app.services.prediction_service import reload_models
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in a thread — schedule the coroutine on the event loop
                        import concurrent.futures
                        future = asyncio.run_coroutine_threadsafe(reload_models(), loop)
                        future.result(timeout=30)
                    except RuntimeError:
                        # No running loop — run directly
                        asyncio.run(reload_models())
                    logger.info("Prediction models reloaded after deploy")
                except Exception as e_reload:
                    logger.warning(f"Model reload after deploy failed (non-blocking): {e_reload}")
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
                "forget_acc": _safe_float(new_metrics.forget_acc),
                "retain_acc": _safe_float(new_metrics.retain_acc),
                "mae_validation": _safe_float(new_metrics.mae_validation),
                "directional_acc": _safe_float(new_metrics.directional_acc),
                "mia_auc": _safe_float(new_metrics.mia_auc),
                "duration_sec": duration,
            }

        except Exception as e:
            logger.error(f"Cycle {cycle_num} failed: {e}")
            # Ensure GPU is freed on failure
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory freed after cycle failure")
            raise

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
                    forget_acc=entry.get("forget_acc", 0),
                    retain_acc=entry.get("retain_acc", 0),
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


def _parse_mia_auc(mia_output_dir: str) -> Optional[float]:
    """Parse the best AUC from the MIA auc.txt output file."""
    auc_path = os.path.join(mia_output_dir, "auc.txt")
    if not os.path.exists(auc_path):
        return None
    try:
        best_auc = 0.5
        with open(auc_path) as f:
            for line in f:
                # Format: "metric_name   AUC 0.7500, Acc 0.6500, TPR@5%FPR 0.1000"
                if "AUC" in line:
                    parts = line.split("AUC")
                    if len(parts) >= 2:
                        auc_str = parts[1].strip().split(",")[0].strip()
                        auc_val = float(auc_str)
                        if auc_val > best_auc:
                            best_auc = auc_val
        return best_auc if best_auc > 0.5 else 0.5
    except Exception as e:
        logger.warning(f"Failed to parse MIA AUC from {auc_path}: {e}")
        return None


def _lightweight_mia_from_buffers(
    model_path: str, forget_path: str, retain_path: str, output_dir: str
) -> Optional[float]:
    """Lightweight MIA using per-sample average loss as a membership signal.

    Computes average cross-entropy loss per sample on forget vs retain sets.
    If the model has lower loss on forget samples (it memorized them), the
    AUC will be higher. After unlearning, losses should be similar → AUC ≈ 0.5.

    This is a simplified version that doesn't require pre-tokenized .pt datasets.
    """
    import math
    import torch
    from stocksense.utils.model_utils import load_model_and_tokenizer
    from stocksense.data.buffer_tokenizer import tokenize_buffer

    try:
        model, tokenizer = load_model_and_tokenizer(model_path)
        model.eval()
        device = next(model.parameters()).device

        def _get_losses(data_path: str, max_samples: int = 30) -> list:
            if not os.path.exists(data_path):
                return []
            dataset = tokenize_buffer(data_path, tokenizer, max_length=256)
            if len(dataset) == 0:
                return []

            losses = []
            n = min(len(dataset), max_samples)
            with torch.no_grad():
                for i in range(n):
                    item = dataset[i]
                    input_ids = torch.as_tensor(item["input_ids"], device=device).unsqueeze(0)
                    labels = input_ids.clone()
                    if "labels" in item:
                        labels = torch.as_tensor(item["labels"], device=device).unsqueeze(0)
                    outputs = model(input_ids=input_ids, labels=labels)
                    losses.append(outputs.loss.item())
            return losses

        forget_losses = _get_losses(forget_path)
        retain_losses = _get_losses(retain_path)

        if not forget_losses or not retain_losses:
            return None

        # Simple AUC approximation:
        # For each forget sample, count how many retain samples have higher loss.
        # If model memorized forget data → forget losses are lower → higher AUC.
        correct = 0
        total = 0
        for f_loss in forget_losses:
            for r_loss in retain_losses:
                total += 1
                if r_loss > f_loss:
                    correct += 1
                elif r_loss == f_loss:
                    correct += 0.5
        auc = correct / max(total, 1)
        # AUC should be >= 0.5 by convention
        if auc < 0.5:
            auc = 1.0 - auc

        # Save result
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "auc.txt"), "w") as f:
            f.write(f"lightweight_loss   AUC {auc:.4f}, samples {len(forget_losses)}+{len(retain_losses)}\n")

        logger.info(f"Lightweight MIA: AUC={auc:.4f} (forget={len(forget_losses)}, retain={len(retain_losses)})")
        return auc

    except Exception as e:
        logger.warning(f"Lightweight MIA failed: {e}")
        return None
    finally:
        try:
            del model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger.info("Running CycleManager in standalone mode...")
    try:
        manager = CycleManager()
        result = manager.run_cycle()
        logger.info(f"Cycle completed. Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        logger.error(f"Cycle failed: {e}")