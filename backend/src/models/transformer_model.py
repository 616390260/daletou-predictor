"""
Transformer 模型

与 LSTM 同类任务：序列 → 下一期号码出现概率。
使用多头自注意力，理论上更能捕捉"跨期号码间相关性"。
同样支持 checkpoint + 增量微调。
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import torch
from torch import nn

from ..config import (
    BACK_COUNT,
    BACK_MAX,
    BACK_MIN,
    DATA_DIR,
    FRONT_COUNT,
    FRONT_MAX,
    FRONT_MIN,
    MONEY_FEATURE_VERSION,
)
from .base import BaseModel, Ticket
from .lstm_model import (
    EXTRA_DIM,
    INPUT_DIM,
    NUMBER_DIM,
    TARGET_DIM,
    WINDOW,
    _build_input_vector,
    _sales_pool_norms,
    _to_multihot,
    FRONT_DIM,
)

CKPT_PATH = DATA_DIR / "transformer_state.pt"
META_PATH = DATA_DIR / "transformer_meta.json"

D_MODEL = 96
NHEAD = 6
NLAYERS = 3
EPOCHS_FULL = 15
EPOCHS_INCR = 6
BATCH_SIZE = 64
LR_FULL = 5e-4
LR_INCR = 2e-4


class LotteryTransformer(nn.Module):
    """
    Transformer Encoder + 汇总 + 线性头
    """

    def __init__(
        self,
        input_dim: int = INPUT_DIM,
        target_dim: int = TARGET_DIM,
        d_model: int = D_MODEL,
        nhead: int = NHEAD,
        nlayers: int = NLAYERS,
    ) -> None:
        super().__init__()
        self.proj = nn.Linear(input_dim, d_model)
        self.pos_emb = nn.Parameter(torch.randn(WINDOW, d_model) * 0.02)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=d_model * 2,
            dropout=0.1, batch_first=True, activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=nlayers)
        self.head = nn.Sequential(
            nn.Linear(d_model, d_model), nn.GELU(), nn.Linear(d_model, target_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.proj(x) + self.pos_emb[None, : x.size(1), :]
        h = self.encoder(h)
        last = h[:, -1, :]
        return torch.sigmoid(self.head(last))


def _prepare_tensors(history: pd.DataFrame) -> Tuple[torch.Tensor, torch.Tensor]:
    sales_max, pool_max = _sales_pool_norms(history)
    inputs = np.stack(
        [_build_input_vector(r, sales_max, pool_max) for r in history.itertuples(index=False)]
    )
    targets = np.stack(
        [_to_multihot(r.front, r.back) for r in history.itertuples(index=False)]
    )
    X_list, y_list = [], []
    for i in range(len(inputs) - WINDOW):
        X_list.append(inputs[i : i + WINDOW])
        y_list.append(targets[i + WINDOW])
    X = torch.tensor(np.stack(X_list), dtype=torch.float32)
    y = torch.tensor(np.stack(y_list), dtype=torch.float32)
    return X, y


def _train_epochs(
    model: nn.Module, X: torch.Tensor, y: torch.Tensor, device: torch.device,
    epochs: int, lr: float, tag: str,
) -> float:
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(X, y), batch_size=BATCH_SIZE, shuffle=True
    )
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()
    last = 0.0
    model.train()
    for epoch in range(epochs):
        total = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
            total += loss.item() * len(xb)
        last = total / len(X)
        print(f"[Transformer·{tag}] epoch {epoch + 1}/{epochs}  loss={last:.4f}")
    return last


class TransformerModel(BaseModel):
    """
    Transformer 序列模型（带 checkpoint + 增量微调）
    """

    name = "transformer"

    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _load_meta(self) -> dict:
        if META_PATH.exists():
            try:
                meta = json.loads(META_PATH.read_text())
                return meta if meta.get("money_feature_version") == MONEY_FEATURE_VERSION else {}
            except Exception:
                pass
        return {}

    def _save_meta(self, meta: dict) -> None:
        META_PATH.write_text(json.dumps({**meta, "money_feature_version": MONEY_FEATURE_VERSION}, ensure_ascii=False, indent=2))

    def _ensure_model(self, history: pd.DataFrame) -> LotteryTransformer:
        meta = self._load_meta()
        latest_issue = str(history.iloc[-1]["issue"])
        model = LotteryTransformer().to(self.device)

        if CKPT_PATH.exists() and meta.get("last_trained_issue"):
            try:
                model.load_state_dict(torch.load(CKPT_PATH, map_location=self.device))
                print(f"[Transformer] 加载 checkpoint，上次训到 {meta['last_trained_issue']}")
            except Exception as e:
                print(f"[Transformer] checkpoint 加载失败（{e}），切换全量训练")
                meta = {}

        if not meta.get("last_trained_issue"):
            print("[Transformer] 首次训练（全量）")
            X, y = _prepare_tensors(history)
            loss = _train_epochs(model, X, y, self.device, EPOCHS_FULL, LR_FULL, "full")
            torch.save(model.state_dict(), CKPT_PATH)
            self._save_meta(
                {"last_trained_issue": latest_issue, "last_loss": loss, "updates": 1}
            )
            return model

        if meta["last_trained_issue"] != latest_issue:
            new_count = (
                (history["issue"].astype(str) > meta["last_trained_issue"]).sum()
            )
            replay = max(60, new_count * 5)
            window = history.tail(replay + WINDOW)
            print(f"[Transformer] 增量微调：新增 {new_count} 期 + 回放 {replay} 期")
            X, y = _prepare_tensors(window)
            loss = _train_epochs(model, X, y, self.device, EPOCHS_INCR, LR_INCR, "incr")
            torch.save(model.state_dict(), CKPT_PATH)
            self._save_meta({
                "last_trained_issue": latest_issue,
                "last_loss": loss,
                "updates": meta.get("updates", 0) + 1,
            })
        else:
            print(f"[Transformer] 已是最新训练 ({latest_issue})，跳过训练")

        return model

    def _predict_probs(self, history: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        model = self._ensure_model(history)
        tail = history.tail(WINDOW)
        sales_max, pool_max = _sales_pool_norms(history)
        seq = np.stack(
            [_build_input_vector(r, sales_max, pool_max) for r in tail.itertuples(index=False)]
        )
        x = torch.tensor(seq[None, ...], dtype=torch.float32).to(self.device)
        model.eval()
        with torch.no_grad():
            out = model(x).cpu().numpy()[0]
        return out[:FRONT_DIM], out[FRONT_DIM:]

    def _sample(self, probs: np.ndarray, k: int, lo: int, seed: int) -> List[int]:
        rng = random.Random(seed)
        p = probs.astype(np.float64).copy() + 1e-6
        picked: List[int] = []
        for _ in range(k):
            s = p.sum()
            if s <= 0:
                remaining = [i for i in range(len(p)) if i + lo not in picked]
                picked.append(rng.choice(remaining) + lo)
                continue
            norm = p / s
            pick = rng.random()
            acc = 0.0
            for i, pi in enumerate(norm):
                acc += pi
                if acc >= pick:
                    picked.append(i + lo)
                    p[i] = 0
                    break
        return picked

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        front_p, back_p = self._predict_probs(history)
        front = self._sample(front_p, FRONT_COUNT, FRONT_MIN, seed=11000 + seed)
        back = self._sample(back_p, BACK_COUNT, BACK_MIN, seed=11500 + seed)
        return Ticket(front=front, back=back)
