"""
GradientAscentTrainer — Emergency fast unlearning.

Maximizes loss on the forget set to aggressively erase poisoned patterns.
Use only for critical data corruption events.

Adapted from llm_unlearn/method/gradient_ascent.py.
"""

from transformers import Trainer
from transformers.utils import is_apex_available

if is_apex_available():
    from apex import amp


class GradientAscentTrainer(Trainer):
    """Trainer that negates loss for gradient ascent (maximizes loss)."""

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        """Compute the negative of the mean loss for gradient ascent."""
        outputs = model(**inputs)

        loss_tensor = (
            outputs["loss"]
            if isinstance(outputs, dict) and "loss" in outputs
            else outputs[0]
        )

        loss = loss_tensor.mean()

        # Gradient ascent → maximize loss
        return (-loss, outputs) if return_outputs else -loss
