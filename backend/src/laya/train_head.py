"""Reuse the local Laya trainer with a frozen encoder and a portable decision head."""
from __future__ import annotations

import hashlib
import runpy
import sys
from pathlib import Path


def main() -> None:
    """Train only head parameters without editing the existing SEO trainer."""
    import torch
    import laya.common
    import safetensors.torch

    torch.manual_seed(20261014)
    original_build = laya.common.build_model
    original_save = safetensors.torch.save_file

    def build_head(config, *, encoder_dir, **kwargs):
        base = Path(encoder_dir).resolve().parent
        config.update(adapter_type="head-only", base_model_path=str(base),
                      base_checkpoint_sha256=hashlib.sha256((base / "model.safetensors").read_bytes()).hexdigest())
        model = original_build(config, encoder_dir=encoder_dir, **kwargs)
        for parameter in model.encoder.parameters():
            parameter.requires_grad_(False)
        model.encoder.gradient_checkpointing_enable = lambda **kwargs: None
        original_train = model.train

        def train(mode=True):
            original_train(mode)
            model.encoder.eval()
            return model

        model.train = train
        return model

    def save_head(state, filename, **kwargs):
        return original_save({key: value for key, value in state.items()
                              if not key.startswith("encoder.")}, filename, **kwargs)

    laya.common.build_model = build_head
    safetensors.torch.save_file = save_head
    trainer = Path.home() / "laya-lab/train_local.py"
    sys.argv[0] = str(trainer)
    runpy.run_path(str(trainer), run_name="__main__")


if __name__ == "__main__":
    main()
