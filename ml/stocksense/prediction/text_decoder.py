"""
text_decoder.py — Parse generated text → price predictions.

Extracts OHLCV values from model-generated text using regex matching
against the window text format specification.
"""

import re
from typing import Optional


# Regex to extract OHLCV fields from generated text
_FIELD_PATTERN = re.compile(
    r"(date|open|high|low|close|vol)=([\d\-]+\.?\d*)"
)


def parse(generated_text: str) -> Optional[dict]:
    """Parse model-generated text into numeric predictions.

    Expected format:
        date=2024-11-04 open=222.50 high=224.00 low=221.00 close=223.50 vol=38000000

    Args:
        generated_text: Raw text output from the model.

    Returns:
        Dict with {open, high, low, close, vol} as floats, or None if parsing fails.
    """
    if not generated_text or not generated_text.strip():
        return None

    matches = _FIELD_PATTERN.findall(generated_text)
    if not matches:
        return None

    result = {}
    for field_name, value in matches:
        if field_name == "date":
            result["date"] = value
            continue
        try:
            if field_name == "vol":
                result["vol"] = int(float(value))
            else:
                result[field_name] = float(value)
        except (ValueError, TypeError):
            continue

    # Require at least close price
    required = ["close"]
    if not all(k in result for k in required):
        return None

    # Fill missing fields with defaults based on close
    close = result["close"]
    result.setdefault("open", close)
    result.setdefault("high", close * 1.005)
    result.setdefault("low", close * 0.995)
    result.setdefault("vol", 0)

    return result


def format_prediction(pred: dict) -> str:
    """Format a prediction dict back into the text format."""
    parts = []
    if "date" in pred:
        parts.append(f"date={pred['date']}")
    parts.append(f"open={pred.get('open', 0):.2f}")
    parts.append(f"high={pred.get('high', 0):.2f}")
    parts.append(f"low={pred.get('low', 0):.2f}")
    parts.append(f"close={pred.get('close', 0):.2f}")
    parts.append(f"vol={int(pred.get('vol', 0))}")
    return " ".join(parts)
