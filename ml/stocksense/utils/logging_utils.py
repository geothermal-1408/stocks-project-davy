"""Structured logging + optional wandb integration."""

import logging
import os
import sys
from typing import Optional


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Get a configured logger with consistent formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                datefmt="%m/%d/%Y %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def setup_logging(
    log_dir: Optional[str] = None,
    level: int = logging.INFO,
) -> None:
    """Configure root logging with optional file output."""
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(
            logging.FileHandler(os.path.join(log_dir, "run.log"))
        )
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        handlers=handlers,
        level=level,
    )


def init_wandb(project: str = "StockSense", run_name: Optional[str] = None):
    """Initialize wandb if available, otherwise return a shim."""
    try:
        import wandb as _wm

        _KEY = os.environ.get("WANDB_API_KEY", "").strip()
        if _KEY:
            _wm.login(key=_KEY)
        else:
            os.environ.setdefault("WANDB_MODE", "offline")
            _wm.login(anonymous="allow")
        _wm.init(project=project, name=run_name)
        return _wm
    except Exception as e:
        print(f"[wandb] Disabled: {e}")
        return _WandbShim()


class _WandbShim:
    """No-op wandb replacement."""

    class run:
        name = ""

    @staticmethod
    def log(*a, **kw):
        pass

    @staticmethod
    def login(*a, **kw):
        pass

    @staticmethod
    def init(*a, **kw):
        pass
