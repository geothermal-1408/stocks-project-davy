"""
predictor.py — Load model + generate next-step stock predictions.

Singleton predictor that loads the current deployed model, generates
N temperature samples, decodes text → prices, and returns confidence bands.
"""

import logging
import os
import time
from typing import Optional

import torch

from stocksense.prediction.text_decoder import parse
from stocksense.prediction.confidence import (
    PredictionResult,
    build_prediction_result,
)
from stocksense.utils.model_utils import load_model_and_tokenizer

logger = logging.getLogger(__name__)


class StockPredictor:
    """Singleton stock price predictor.

    Loads the current deployed model and generates predictions via
    temperature sampling.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_samples: int = 10,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_new_tokens: int = 64,
    ):
        self.model_path = model_path or os.environ.get(
            "MODEL_PATH", "./output/stock/current"
        )
        self.n_samples = n_samples
        self.temperature = temperature
        self.top_p = top_p
        self.max_new_tokens = max_new_tokens

        self._model = None
        self._tokenizer = None
        self._loaded_path = None
        self._cycle = -1

    def _load_model(self, force: bool = False) -> None:
        """Load or reload the model."""
        # Resolve symlink only if it's a local path
        if self.model_path.startswith(".") or self.model_path.startswith("/") or self.model_path.startswith("~"):
            real_path = os.path.realpath(self.model_path)
        else:
            real_path = self.model_path

        # Resolve cases where `real_path` is a wrapper directory (e.g. contains
        # a single subfolder like 'stocksense-qwen/...'). Try to locate a
        # recognizable model directory by searching for common artifacts
        # (config.json, tokenizer files, or weight files) within up to two
        # levels of depth.
        def _looks_like_model_dir(p: str) -> bool:
            if not os.path.isdir(p):
                return False
            candidates = ["config.json", "tokenizer.json", "tokenizer_config.json", "pytorch_model.bin"]
            for c in candidates:
                if os.path.exists(os.path.join(p, c)):
                    return True
            # safetensors or bin weight files
            for fp in os.listdir(p):
                if fp.endswith(".safetensors") or fp.endswith(".bin"):
                    return True
            return False

        if not _looks_like_model_dir(real_path):
            if os.path.isdir(real_path):
                # First look at immediate children
                for entry in os.listdir(real_path):
                    subdir = os.path.join(real_path, entry)
                    if _looks_like_model_dir(subdir):
                        real_path = subdir
                        logger.info(f"Found model in subdirectory: {real_path}")
                        break
                else:
                    # Then look one level deeper (grandchildren)
                    for entry in os.listdir(real_path):
                        subdir = os.path.join(real_path, entry)
                        if not os.path.isdir(subdir):
                            continue
                        for g in os.listdir(subdir):
                            grand = os.path.join(subdir, g)
                            if _looks_like_model_dir(grand):
                                real_path = grand
                                logger.info(f"Found model in nested subdirectory: {real_path}")
                                break
                        if _looks_like_model_dir(real_path):
                            break

        if not force and self._loaded_path == real_path and self._model is not None:
            return

        logger.info(f"Loading model from {real_path}")
        self._model, self._tokenizer = load_model_and_tokenizer(real_path)
        self._loaded_path = real_path
        self._model.eval()

        if torch.cuda.is_available():
            self._model = self._model.to("cuda")

        logger.info("Model loaded successfully")

    def predict(
        self,
        window_text: str,
        ticker: str = "AAPL",
        prev_close: Optional[float] = None,
        n_samples: Optional[int] = None,
    ) -> PredictionResult:
        """Generate price predictions from a window text.

        Args:
            window_text: 30-day OHLCV window in text format.
            ticker: Stock ticker symbol.
            prev_close: Previous day's close price for direction.
            n_samples: Number of temperature samples (overrides default).

        Returns:
            PredictionResult with mean predictions and confidence bands.
        """
        self._load_model()
        n = n_samples or self.n_samples
        device = next(self._model.parameters()).device

        t0 = time.time()
        inputs = self._tokenizer(
            window_text, return_tensors="pt"
        ).to(device)

        samples = []
        for _ in range(n):
            with torch.no_grad():
                out = self._model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=True,
                    temperature=self.temperature,
                    top_p=self.top_p,
                )
            generated = self._tokenizer.decode(
                out[0][inputs.input_ids.shape[1] :],
                skip_special_tokens=True,
            )
            parsed = parse(generated)
            if parsed:
                samples.append(parsed)

        latency_ms = (time.time() - t0) * 1000

        result = build_prediction_result(
            samples=samples,
            ticker=ticker,
            prev_close=prev_close,
            model_cycle=self._cycle,
            latency_ms=latency_ms,
        )

        logger.info(
            f"Prediction for {ticker}: close={result.close:.2f} "
            f"({result.n_valid_samples}/{n} valid samples, "
            f"{latency_ms:.0f}ms)"
        )
        return result

    def reload(self) -> None:
        """Force reload the model (e.g., after a new cycle deployment)."""
        self._load_model(force=True)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", default="./output/stock/current")
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--window_file", help="JSONL file with window text")
    parser.add_argument("--samples", type=int, default=10)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    predictor = StockPredictor(
        model_path=args.model_path, n_samples=args.samples
    )

    if args.window_file:
        import json
        with open(args.window_file) as f:
            for line in f:
                entry = json.loads(line)
                result = predictor.predict(entry["text"], args.ticker)
                print(json.dumps(result.to_dict(), indent=2))
