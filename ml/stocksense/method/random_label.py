"""
RandomLabelTrainer — Unlearning via random label replacement.

Replaces the ground-truth labels with random token IDs so the model
learns incorrect associations for the forget set, effectively "unlearning"
the poisoned patterns.

Adapted from llm_unlearn/method/random_label.py.
"""

import torch
from transformers import Trainer


class RandomLabelTrainer(Trainer):
    """Trainer that randomizes labels to induce forgetting.

    For each batch, replaces non-padding label tokens with random token IDs
    drawn uniformly from the vocabulary. The model then trains on these
    incorrect targets, disrupting learned associations.
    """

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        """Compute loss with randomized labels."""
        # Clone labels to avoid modifying the original
        labels = inputs["labels"].clone()
        vocab_size = model.config.vocab_size

        # Create a mask of valid (non-padding) tokens
        valid_mask = labels != -100

        # Replace valid tokens with random token IDs
        num_valid = valid_mask.sum().item()
        if num_valid > 0:
            random_ids = torch.randint(
                0, vocab_size, (num_valid,),
                device=labels.device, dtype=labels.dtype,
            )
            labels[valid_mask] = random_ids

        # Forward pass with randomized labels
        inputs["labels"] = labels
        outputs = model(**inputs)
        loss = outputs.loss

        return (loss, outputs) if return_outputs else loss