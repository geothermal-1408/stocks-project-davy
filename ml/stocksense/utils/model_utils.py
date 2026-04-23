"""
Model loading utilities for StockSense.
Adapted from llm_unlearn/utils/utils.py — handles safetensors fallback,
LFS pointer detection, and robust multi-variant loading.
"""

import glob
import json
import os
from typing import Dict, List, Optional, Tuple

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .tokenizer_resize import smart_tokenizer_and_embedding_resize


def load_model_and_tokenizer(
    model_path_or_name: str,
    auto_device: bool = False,
    model_max_length: int = 4096,
):
    """Load a causal LM model and its tokenizer with robust fallback logic.

    Handles:
    - safetensors vs PyTorch shard fallback
    - Git LFS pointer detection
    - pre-Ampere GPU compatibility (no bf16)
    """
    torch_dtype = torch.float32

    params = {
        "torch_dtype": torch_dtype,
        "trust_remote_code": True,
        "use_safetensors": True,
    }
    if auto_device:
        params["device_map"] = "auto"

    def _looks_like_git_lfs_pointer(file_path: str) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(200)
            return b"git-lfs.github.com/spec" in head
        except Exception:
            return False

    def _raise_incomplete_weights_error(original_error: Exception) -> None:
        msg = (
            "Model weights appear to be incomplete/corrupted "
            "(often caused by missing Git LFS downloads).\n"
            f"Tried loading from: {model_path_or_name!r}\n"
            f"Original error: {type(original_error).__name__}: {original_error}\n\n"
            "If you cloned this repo, install Git LFS and pull:\n"
            "  git lfs install && git lfs pull\n\n"
            "Or re-download via Hugging Face snapshot_download."
        )
        raise RuntimeError(msg) from original_error

    def _get_index_expected_shards(
        model_dir: str, index_filename: str
    ) -> Tuple[str, List[str], int]:
        index_path = os.path.join(model_dir, index_filename)
        if not os.path.isfile(index_path):
            return index_path, [], 0
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        expected_total = int(
            index.get("metadata", {}).get("total_size", 0) or 0
        )
        weight_map = index.get("weight_map", {}) or {}
        shard_names = sorted(set(weight_map.values()))
        return index_path, shard_names, expected_total

    def _choose_weight_format_or_raise(model_dir: str) -> Dict:
        st_index, st_shards, st_total = _get_index_expected_shards(
            model_dir, "model.safetensors.index.json"
        )
        pt_index, pt_shards, pt_total = _get_index_expected_shards(
            model_dir, "pytorch_model.bin.index.json"
        )

        st_present = [
            s
            for s in st_shards
            if os.path.isfile(os.path.join(model_dir, s))
        ]
        pt_present = [
            s
            for s in pt_shards
            if os.path.isfile(os.path.join(model_dir, s))
        ]

        if st_shards and len(st_present) == len(st_shards) and st_total:
            actual_total = sum(
                os.path.getsize(os.path.join(model_dir, s))
                for s in st_present
            )
            if actual_total < int(0.98 * int(st_total)):
                _raise_incomplete_weights_error(
                    RuntimeError(
                        f"Incomplete safetensors: {actual_total} bytes, "
                        f"expected ~{int(st_total)} bytes"
                    )
                )

        if st_shards and len(st_present) == len(st_shards):
            return {"use_safetensors": True}
        if pt_shards and len(pt_present) == len(pt_shards):
            return {"use_safetensors": False}

        if not (os.path.isfile(st_index) or os.path.isfile(pt_index)):
            return {}

        missing_msgs = []
        if st_shards and len(st_present) != len(st_shards):
            missing = [s for s in st_shards if s not in st_present]
            missing_msgs.append(
                f"- Missing safetensors: {', '.join(missing[:5])}"
            )
        if pt_shards and len(pt_present) != len(pt_shards):
            missing = [s for s in pt_shards if s not in pt_present]
            missing_msgs.append(
                f"- Missing PyTorch: {', '.join(missing[:5])}"
            )

        total_hint = max(st_total, pt_total)
        hint = (
            "Local model directory has index file(s) but not the weight shards.\n"
            + (
                f"Expected total size: ~{total_hint / 1e9:.2f} GB\n"
                if total_hint
                else ""
            )
            + "\n".join(missing_msgs)
        )
        _raise_incomplete_weights_error(RuntimeError(hint))
        return {}

    # If loading from a local folder, pick a viable weight format early.
    if isinstance(model_path_or_name, str) and os.path.isdir(
        model_path_or_name
    ):
        try:
            params.update(_choose_weight_format_or_raise(model_path_or_name))
        except RuntimeError:
            raise
        except Exception:
            pass

    def _from_pretrained_with_retries() -> AutoModelForCausalLM:
        base = dict(params)
        variants = [dict(base)]
        if base.get("use_safetensors", None) is True:
            can_fallback_to_pt = True
            if isinstance(model_path_or_name, str) and os.path.isdir(
                model_path_or_name
            ):
                _pt_index, pt_shards, _pt_total = _get_index_expected_shards(
                    model_path_or_name, "pytorch_model.bin.index.json"
                )
                if pt_shards:
                    can_fallback_to_pt = all(
                        os.path.isfile(os.path.join(model_path_or_name, s))
                        for s in pt_shards
                    )
                else:
                    can_fallback_to_pt = False
            if can_fallback_to_pt:
                v = dict(base)
                v["use_safetensors"] = False
                variants.append(v)

        last_error: Optional[Exception] = None
        for local_params in variants:
            try:
                return AutoModelForCausalLM.from_pretrained(
                    model_path_or_name, **local_params
                )
            except TypeError as e:
                last_error = e
                if "use_flash_attention_2" in str(e):
                    continue
                raise
            except Exception as e:
                last_error = e
                name = type(e).__name__
                text = str(e)
                if (
                    "safetensor" in text.lower()
                    or name.lower() == "safetensorerror"
                ):
                    continue
                raise

        assert last_error is not None
        if isinstance(model_path_or_name, str) and os.path.isdir(
            model_path_or_name
        ):
            for fp in glob.glob(
                os.path.join(model_path_or_name, "*.safetensors")
            ):
                if _looks_like_git_lfs_pointer(fp):
                    _raise_incomplete_weights_error(last_error)
            for fp in glob.glob(
                os.path.join(model_path_or_name, "*.bin")
            ):
                if _looks_like_git_lfs_pointer(fp):
                    _raise_incomplete_weights_error(last_error)
        raise last_error

    model = _from_pretrained_with_retries()

    tokenizer = AutoTokenizer.from_pretrained(
        model_path_or_name,
        padding_side="right",
        trust_remote_code=True,
        model_max_length=model_max_length,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.config.pad_token_id = tokenizer.pad_token_id

    return model, tokenizer
