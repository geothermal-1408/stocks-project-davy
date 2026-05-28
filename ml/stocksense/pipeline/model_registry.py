"""
model_registry.py — Version tracking + rollback for deployed models.

Manages the output/stock/current symlink that points to the latest
deployed model checkpoint.
"""

import json
import logging
import os
import platform
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

OUTPUT_BASE = os.environ.get("OUTPUT_BASE", "./output/stock")


class ModelRegistry:
    """Manages model versions and the 'current' deployment symlink."""

    def __init__(self, output_base: Optional[str] = None):
        self.output_base = output_base or OUTPUT_BASE
        self.current_dir = os.path.join(self.output_base, "current")
        self.current_link = os.path.join(self.current_dir, "stocksense-qwen")

    def get_current_model_path(self) -> Optional[str]:
        """Get the path to the currently deployed model."""
        if os.path.exists(self.current_link):
            return os.path.realpath(self.current_link)
        # Fallback: check for finetune dir
        ft = os.path.join(self.output_base, "finetune")
        if os.path.exists(ft):
            return ft
        return None

    def get_cycle_num(self) -> int:
        """Get the current deployed cycle number."""
        path = self.get_current_model_path()
        if not path:
            return 0
        # Parse cycle_NNN from path
        for part in path.replace("\\", "/").split("/"):
            if part.startswith("cycle_"):
                try:
                    return int(part.split("_")[1])
                except (IndexError, ValueError):
                    pass
        return 0

    def get_next_cycle_num(self) -> int:
        """Get the next cycle number."""
        return self.get_cycle_num() + 1

    def get_cycle_dir(self, cycle_num: int) -> str:
        """Get the directory path for a specific cycle."""
        return os.path.join(
            self.output_base, f"cycle_{cycle_num:03d}"
        )

    def deploy_model(self, cycle_num: int) -> str:
        """Deploy a model by updating the 'current' symlink.

        Points current → cycle_NNN/superlearned/

        Returns:
            Path to the deployed model.
        """
        cycle_dir = self.get_cycle_dir(cycle_num)
        superlearned = os.path.join(cycle_dir, "superlearned")

        if not os.path.exists(superlearned):
            # Fall back to unlearned if superlearned doesn't exist
            superlearned = os.path.join(cycle_dir, "unlearned")

        if not os.path.exists(superlearned):
            raise FileNotFoundError(
                f"No model found for cycle {cycle_num} at {cycle_dir}"
            )

        # Ensure current directory exists
        os.makedirs(self.current_dir, exist_ok=True)

        # Remove old symlink
        if os.path.exists(self.current_link) or os.path.islink(
            self.current_link
        ):
            if os.path.islink(self.current_link):
                os.unlink(self.current_link)
            elif os.path.isdir(self.current_link):
                # On Windows, might be a junction or directory with contents
                shutil.rmtree(self.current_link)

        # Create symlink (or junction on Windows)
        try:
            os.symlink(
                os.path.abspath(superlearned),
                self.current_link,
                target_is_directory=True,
            )
        except OSError:
            # Fallback for Windows without symlink privilege
            if platform.system() == "Windows":
                # Use directory junction instead
                import subprocess
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J",
                     self.current_link, os.path.abspath(superlearned)],
                    check=True,
                )
            else:
                raise

        logger.info(
            f"Deployed cycle {cycle_num}: current → {superlearned}"
        )
        return superlearned

    def rollback_model(self, to_cycle: int) -> str:
        """Rollback to a previous cycle."""
        logger.info(f"Rolling back to cycle {to_cycle}")
        return self.deploy_model(to_cycle)

    def log_cycle(
        self,
        cycle_num: int,
        method: str,
        metrics: dict,
        deployed: bool,
        gate_failure: Optional[str] = None,
        duration_sec: int = 0,
    ) -> None:
        """Log cycle metadata to cycle_history.json."""
        log_dir = os.path.join(
            os.path.dirname(self.output_base), "logs"
        )
        os.makedirs(log_dir, exist_ok=True)
        history_path = os.path.join(log_dir, "cycle_history.json")

        history = []
        if os.path.exists(history_path):
            with open(history_path) as f:
                history = json.load(f)

        from datetime import datetime
        entry = {
            "cycle_num": cycle_num,
            "method": method,
            "deployed": deployed,
            "gate_failure": gate_failure,
            "duration_sec": duration_sec,
            "timestamp": datetime.utcnow().isoformat(),
            **metrics,
        }
        history.append(entry)

        with open(history_path, "w") as f:
            json.dump(history, f, indent=2)

        logger.info(f"Logged cycle {cycle_num} to {history_path}")
