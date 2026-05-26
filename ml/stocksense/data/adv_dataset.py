"""
adv_dataset.py — AdvSupervisedDataset for Ascent+Descent / AKL trainers.

Interleaves forget samples (factor=-1) with retain samples (factor>0)
for simultaneous gradient ascent/descent training.

Adapted from llm_unlearn/utils/ad_tokenizer.py.
"""

import datasets
from torch.utils.data import Dataset
from tqdm import trange


class AdvSupervisedDataset(Dataset):
    """Dataset for adversarial supervised fine-tuning (AD/AKL).

    Each sample includes input_ids, labels, attention_mask, and a 'factor'
    field: -1 for forget (ascent), positive for retain (descent).
    """

    def __init__(self, negative_data_dict, positive_data_dict, data_args):
        super().__init__()

        self.input_ids = []
        self.labels = []
        self.attention_mask = []
        self.factor = []

        if data_args is None:
            # Empty dataset (used by .select())
            return

        print("Formatting inputs...")
        neg = negative_data_dict.to_dict() if hasattr(negative_data_dict, "to_dict") else negative_data_dict
        pos = positive_data_dict.to_dict() if hasattr(positive_data_dict, "to_dict") else positive_data_dict

        pr = data_args.positive_ratio

        for i in trange(len(neg["input_ids"])):
            self.input_ids.append(neg["input_ids"][i])
            self.labels.append(neg["labels"][i])
            self.attention_mask.append(neg["attention_mask"][i])
            self.factor.append(-1)

            pos_chunk = pos["input_ids"][i * pr : (i + 1) * pr]
            pos_chunk_len = len(pos_chunk)
            self.input_ids.extend(pos_chunk)
            self.labels.extend(pos["labels"][i * pr : (i + 1) * pr])
            self.attention_mask.extend(pos["attention_mask"][i * pr : (i + 1) * pr])
            self.factor.extend([data_args.positive_factor] * pos_chunk_len)

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, i):
        return dict(
            input_ids=self.input_ids[i],
            labels=self.labels[i],
            attention_mask=self.attention_mask[i],
            factor=self.factor[i],
        )

    def select(self, selection_range):
        new_ds = AdvSupervisedDataset(
            datasets.Dataset.from_dict({"input_ids": []}),
            datasets.Dataset.from_dict({"input_ids": []}),
            None,
        )
        new_ds.input_ids = [self.input_ids[i] for i in selection_range]
        new_ds.labels = [self.labels[i] for i in selection_range]
        new_ds.attention_mask = [self.attention_mask[i] for i in selection_range]
        new_ds.factor = [self.factor[i] for i in selection_range]
        return new_ds
