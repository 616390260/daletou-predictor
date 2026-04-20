"""
LSTM 神经网络模型（支持增量学习）

训练策略：
- 首次训练：全量历史数据跑 EPOCHS_FULL 轮
- 增量训练：加载上次 checkpoint，热启动后只在"新增数据 + 滑窗末尾样本"上跑 EPOCHS_INCR 轮
- checkpoint 文件：data/lstm_state.pt
- 元数据：data/lstm_meta.json（记录训练到哪一期、训练轮次累计等）
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ..config import (
    BACK_COUNT,
    BACK_MAX,
    BACK_MIN,
    DATA_DIR,
    FRONT_COUNT,
    FRONT_MAX,
    FRONT_MIN,
)
from .base import BaseModel, Ticket

FRONT_DIM = FRONT_MAX - FRONT_MIN + 1
BACK_DIM = BACK_MAX - BACK_MIN + 1
NUMBER_DIM = FRONT_DIM + BACK_DIM
# 额外特征：周几 one-hot(7) + 月份 one-hot(12) + 归一化销量 + 归一化奖池 = 21
EXTRA_DIM = 7 + 12 + 2
INPUT_DIM = NUMBER_DIM + EXTRA_DIM
TARGET_DIM = NUMBER_DIM

WINDOW = 10
HIDDEN = 128
EPOCHS_FULL = 20
EPOCHS_INCR = 8
BATCH_SIZE = 64
LR_FULL = 1e-3
LR_INCR = 3e-4

CKPT_PATH = DATA_DIR / "lstm_state.pt"
META_PATH = DATA_DIR / "lstm_meta.json"


class LotteryLSTM(nn.Module):
    """
    输入序列：[号码 multihot (47) + 周几 one-hot (7) + 月份 one-hot (12) + 销量/奖池 (2)]
    输出：下一期各号码出现概率 (47)
    """

    def __init__(
        self, input_dim: int = INPUT_DIM, target_dim: int = TARGET_DIM, hidden: int = HIDDEN
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden, num_layers=2, batch_first=True, dropout=0.2)
        self.fc = nn.Sequential(
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, target_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        return torch.sigmoid(self.fc(last))


def _to_multihot(front: list, back: list) -> np.ndarray:
    """
    号码列表 → 号码维度 multi-hot 向量
    """
    vec = np.zeros(NUMBER_DIM, dtype=np.float32)
    for n in front:
        vec[n - FRONT_MIN] = 1.0
    for n in back:
        vec[FRONT_DIM + n - BACK_MIN] = 1.0
    return vec


def _extra_features(row, sales_max: float, pool_max: float) -> np.ndarray:
    """
    构造附加特征向量：周几 one-hot(7) + 月份 one-hot(12) + 销量/奖池归一化(2)
    """
    vec = np.zeros(EXTRA_DIM, dtype=np.float32)
    date_str = row.draw_date
    try:
        import datetime as dt

        d = dt.datetime.strptime(date_str, "%Y-%m-%d")
        vec[d.weekday()] = 1.0
        vec[7 + (d.month - 1)] = 1.0
    except Exception:
        pass
    sales = getattr(row, "sales", 0) or 0
    pool = getattr(row, "pool", 0) or 0
    vec[7 + 12 + 0] = min(sales / sales_max, 2.0) if sales_max > 0 else 0.0
    vec[7 + 12 + 1] = min(pool / pool_max, 2.0) if pool_max > 0 else 0.0
    return vec


def _build_input_vector(row, sales_max: float, pool_max: float) -> np.ndarray:
    """
    单期完整输入向量（号码 + 附加特征）
    """
    return np.concatenate(
        [_to_multihot(row.front, row.back), _extra_features(row, sales_max, pool_max)]
    )


def _load_meta() -> dict:
    """
    读取元数据
    """
    if META_PATH.exists():
        try:
            return json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_meta(meta: dict) -> None:
    """
    写入元数据
    """
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _sales_pool_norms(history: pd.DataFrame) -> Tuple[float, float]:
    """
    计算销量和奖池的归一化基准（90 分位数），避免极端值拉偏尺度
    """
    sales_arr = history["sales"].to_numpy() if "sales" in history.columns else np.zeros(len(history))
    pool_arr = history["pool"].to_numpy() if "pool" in history.columns else np.zeros(len(history))
    sales_max = float(np.quantile(sales_arr, 0.9)) if len(sales_arr) else 1.0
    pool_max = float(np.quantile(pool_arr, 0.9)) if len(pool_arr) else 1.0
    return max(sales_max, 1.0), max(pool_max, 1.0)


def _prepare_tensors(history: pd.DataFrame) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    把历史数据切成滑窗训练样本

    @returns (X[N, WINDOW, INPUT_DIM], y[N, TARGET_DIM])
    """
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


class LSTMModel(BaseModel):
    """
    LSTM 预测模型，支持增量训练
    """

    name = "lstm"

    def __init__(self) -> None:
        self.model: Optional[LotteryLSTM] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _train_full(self, history: pd.DataFrame) -> Tuple[LotteryLSTM, float]:
        """
        全量训练：在全部历史上跑 EPOCHS_FULL 轮
        """
        X, y = _prepare_tensors(history)
        loader = DataLoader(TensorDataset(X, y), batch_size=BATCH_SIZE, shuffle=True)
        model = LotteryLSTM().to(self.device)
        opt = torch.optim.Adam(model.parameters(), lr=LR_FULL)
        loss_fn = nn.BCELoss()

        model.train()
        last_loss = 0.0
        for epoch in range(EPOCHS_FULL):
            total = 0.0
            for xb, yb in loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                pred = model(xb)
                loss = loss_fn(pred, yb)
                opt.zero_grad()
                loss.backward()
                opt.step()
                total += loss.item() * len(xb)
            last_loss = total / len(X)
            print(f"[LSTM·full] epoch {epoch + 1}/{EPOCHS_FULL}  loss={last_loss:.4f}")
        return model, last_loss

    def _train_incremental(
        self, model: LotteryLSTM, history: pd.DataFrame, last_trained_issue: str
    ) -> Tuple[LotteryLSTM, float]:
        """
        增量训练：从 checkpoint 热启动，只在 last_trained_issue 之后的新数据及其滑窗上微调
        为避免灾难性遗忘，同时采样最近 N 期做 replay buffer
        """
        idx_new = history.index[history["issue"] > last_trained_issue]
        if len(idx_new) == 0:
            print("[LSTM·incr] 无新数据，跳过训练")
            return model, -1.0

        first_new = int(idx_new[0])
        start_idx = max(0, first_new - WINDOW)
        new_slice = history.iloc[start_idx:]

        replay_size = min(400, len(history) - len(new_slice))
        replay = history.iloc[-(len(new_slice) + replay_size) : -len(new_slice)] if replay_size > 0 else history.iloc[:0]
        combined = pd.concat([replay, new_slice], ignore_index=True)

        if len(combined) <= WINDOW:
            print("[LSTM·incr] 样本不足，跳过")
            return model, -1.0

        X, y = _prepare_tensors(combined)
        loader = DataLoader(TensorDataset(X, y), batch_size=BATCH_SIZE, shuffle=True)
        opt = torch.optim.Adam(model.parameters(), lr=LR_INCR)
        loss_fn = nn.BCELoss()

        model.train()
        last_loss = 0.0
        for epoch in range(EPOCHS_INCR):
            total = 0.0
            for xb, yb in loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                pred = model(xb)
                loss = loss_fn(pred, yb)
                opt.zero_grad()
                loss.backward()
                opt.step()
                total += loss.item() * len(xb)
            last_loss = total / len(X)
            print(f"[LSTM·incr] epoch {epoch + 1}/{EPOCHS_INCR}  loss={last_loss:.4f}")
        return model, last_loss

    def _ensure_model(self, history: pd.DataFrame) -> LotteryLSTM:
        """
        智能加载/训练模型：
        - 无 checkpoint → 全量训练
        - 有 checkpoint 且无新数据 → 直接加载
        - 有 checkpoint 且有新数据 → 热启动 + 增量训练
        """
        if self.model is not None:
            return self.model

        latest_issue = history.iloc[-1]["issue"]
        meta = _load_meta()
        last_trained = meta.get("last_trained_issue")

        model = LotteryLSTM().to(self.device)

        if CKPT_PATH.exists() and last_trained:
            model.load_state_dict(torch.load(CKPT_PATH, map_location=self.device))
            print(f"[LSTM] 加载 checkpoint，上次训练到 {last_trained}")
            if last_trained >= latest_issue:
                print("[LSTM] 已是最新，无需重训")
            else:
                model, loss = self._train_incremental(model, history, last_trained)
                if loss >= 0:
                    torch.save(model.state_dict(), CKPT_PATH)
                    meta = {
                        "last_trained_issue": latest_issue,
                        "last_loss": loss,
                        "updates": meta.get("updates", 0) + 1,
                        "mode": "incremental",
                    }
                    _save_meta(meta)
                    print(f"[LSTM] checkpoint 已更新（累计更新 {meta['updates']} 次）")
        else:
            print("[LSTM] 首次训练（全量）")
            model, loss = self._train_full(history)
            torch.save(model.state_dict(), CKPT_PATH)
            _save_meta(
                {
                    "last_trained_issue": latest_issue,
                    "last_loss": loss,
                    "updates": 1,
                    "mode": "full",
                }
            )

        model.eval()
        self.model = model
        return model

    def _predict_probs(self, history: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        用最后 WINDOW 期推理，得到前区/后区概率向量
        """
        model = self._ensure_model(history)
        tail = history.tail(WINDOW)
        sales_max, pool_max = _sales_pool_norms(history)
        seq = np.stack(
            [_build_input_vector(r, sales_max, pool_max) for r in tail.itertuples(index=False)]
        )
        x = torch.tensor(seq[None, ...], dtype=torch.float32).to(self.device)
        with torch.no_grad():
            out = model(x).cpu().numpy()[0]
        return out[:FRONT_DIM], out[FRONT_DIM:]

    @staticmethod
    def _sample_topk_softly(
        probs: np.ndarray, k: int, lo: int, seed: int, temperature: float = 0.5
    ) -> list:
        """
        软 top-K 抽样
        """
        rng = random.Random(seed)
        safe = np.clip(probs, 1e-6, None)
        logits = np.log(safe) / max(temperature, 1e-3)
        exp = np.exp(logits - logits.max())
        p = exp / exp.sum()

        picked: list = []
        available = p.copy()
        for _ in range(k):
            s = available.sum()
            if s <= 0:
                remaining = [i for i in range(len(p)) if i + lo not in picked]
                picked.append(rng.choice(remaining) + lo)
                continue
            norm = available / s
            pick = rng.random()
            acc = 0.0
            for i, pi in enumerate(norm):
                acc += pi
                if acc >= pick:
                    picked.append(i + lo)
                    available[i] = 0
                    break
        return picked

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        front_p, back_p = self._predict_probs(history)
        front = self._sample_topk_softly(front_p, FRONT_COUNT, FRONT_MIN, seed=1000 + seed)
        back = self._sample_topk_softly(back_p, BACK_COUNT, BACK_MIN, seed=2000 + seed)
        return Ticket(front=front, back=back)
