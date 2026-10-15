"""
XGBoost 模型

对每个号码单独训练一棵 gradient boosting 二分类器，预测"下一期是否出现"。
输入特征：
- 过去 WINDOW 期该号码的出现向量（0/1）
- 过去 WINDOW 期该号码的遗漏值
- 最近一期的组合手工特征向量（extract）
- 最近一期的销量/奖池/周几/月份

训练结果全量 retrain（XGBoost 快，可以不做增量）。CPU 友好。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

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
from ..utils.features import extract
from .base import BaseModel, Ticket

WINDOW = 10
CACHE_PATH = DATA_DIR / "xgboost_probs.npz"


def _weekday_month(date_str: str) -> Tuple[int, int]:
    import datetime as dt

    try:
        d = dt.datetime.strptime(date_str, "%Y-%m-%d")
        return d.weekday(), d.month
    except Exception:
        return 0, 1


def _build_dataset(
    history: pd.DataFrame, is_front: bool
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    构造 (X, y, last_x) 三元组：
    - X：训练样本 [N, F]
    - y：目标 [N, K]（multi-label）
    - last_x：最后一行推理输入 [F]
    """
    lo, hi = (FRONT_MIN, FRONT_MAX) if is_front else (BACK_MIN, BACK_MAX)
    k = hi - lo + 1
    key = "front" if is_front else "back"

    presence = np.zeros((len(history), k), dtype=np.float32)
    for i, row in enumerate(history.itertuples(index=False)):
        for num in getattr(row, key):
            presence[i, num - lo] = 1.0

    misses = np.zeros_like(presence)
    current = np.full(k, fill_value=len(history), dtype=np.float32)
    for i in range(len(history)):
        current += 1
        for num_idx in np.where(presence[i] == 1)[0]:
            current[num_idx] = 0
        misses[i] = current

    extras = np.zeros((len(history), 6), dtype=np.float32)
    sales_arr = history.get("sales", pd.Series([0] * len(history))).to_numpy().astype(np.float32)
    pool_arr = history.get("pool", pd.Series([0] * len(history))).to_numpy().astype(np.float32)
    smax = float(np.quantile(sales_arr, 0.9)) or 1.0
    pmax = float(np.quantile(pool_arr, 0.9)) or 1.0
    for i, row in enumerate(history.itertuples(index=False)):
        wd, mo = _weekday_month(row.draw_date)
        feat = extract(row.front, row.back).to_vector()
        extras[i] = np.array(
            [wd / 7.0, mo / 12.0, sales_arr[i] / smax, pool_arr[i] / pmax,
             feat[0] / 150.0,  # sum_front 归一化
             feat[2] / 35.0,   # span_front 归一化
             ], dtype=np.float32
        )

    X_list, y_list = [], []
    for i in range(WINDOW, len(history)):
        feat = np.concatenate([
            presence[i - WINDOW:i].flatten(),
            misses[i - WINDOW:i].flatten() / max(len(history), 1),
            extras[i - 1],
        ])
        X_list.append(feat)
        y_list.append(presence[i])

    last_x = np.concatenate([
        presence[-WINDOW:].flatten(),
        misses[-WINDOW:].flatten() / max(len(history), 1),
        extras[-1],
    ])
    return np.stack(X_list), np.stack(y_list), last_x


class XGBoostModel(BaseModel):
    """
    XGBoost 每号独立二分类器，预测号码出现概率，按概率加权抽样
    """

    name = "xgboost"

    def _get_classifier_cls(self):
        """
        优先使用 XGBoost；加载失败（如 Mac 缺 libomp）时降级为 sklearn HistGradientBoostingClassifier
        """
        try:
            import xgboost as xgb

            def _make():
                return xgb.XGBClassifier(
                    max_depth=4, n_estimators=80, learning_rate=0.1,
                    objective="binary:logistic", eval_metric="logloss",
                    tree_method="hist", nthread=os.cpu_count() or 1, verbosity=0,
                )

            return _make, "xgboost"
        except Exception as e:
            print(f"[XGBoost] xgboost 加载失败 ({e})，降级为 sklearn HistGradientBoostingClassifier")
            from sklearn.ensemble import HistGradientBoostingClassifier

            def _make():
                return HistGradientBoostingClassifier(
                    max_depth=4, max_iter=80, learning_rate=0.1, early_stopping=False,
                )

            return _make, "sklearn"

    def _train_predict(self, history: pd.DataFrame, is_front: bool) -> np.ndarray:
        """
        训练并返回下一期各号码的出现概率
        """
        make_clf, backend = self._get_classifier_cls()
        X, y, last_x = _build_dataset(history, is_front)
        k = y.shape[1]
        probs = np.zeros(k, dtype=np.float32)
        for num_idx in range(k):
            clf = make_clf()
            y_num = y[:, num_idx].astype(int)
            if y_num.sum() == 0:
                probs[num_idx] = 0.0
                continue
            try:
                clf.fit(X, y_num)
                probs[num_idx] = float(clf.predict_proba(last_x[None, :])[0, 1])
            except Exception as e:
                probs[num_idx] = float(y_num.mean())
        return probs

    def _sample(self, probs: np.ndarray, k: int, lo: int, seed: int) -> List[int]:
        """
        按概率向量不放回抽样（加微小噪声避免确定化）
        """
        import random
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

    def _cached_probs(self, history: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        针对同一历史快照只训练一次，避免 4 张投注都重算
        """
        signature = f"money-v{MONEY_FEATURE_VERSION}-{len(history)}-{history.iloc[-1]['issue']}"
        if CACHE_PATH.exists():
            try:
                cache = np.load(CACHE_PATH)
                if cache.get("signature", np.array(["x"]))[0] == signature:
                    return cache["front_p"], cache["back_p"]
            except Exception:
                pass
        print(f"[XGBoost] 训练中，历史规模 {len(history)}...")
        front_p = self._train_predict(history, is_front=True)
        back_p = self._train_predict(history, is_front=False)
        np.savez(
            CACHE_PATH,
            signature=np.array([signature]),
            front_p=front_p,
            back_p=back_p,
        )
        return front_p, back_p

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        front_p, back_p = self._cached_probs(history)
        front = self._sample(front_p, FRONT_COUNT, FRONT_MIN, seed=9000 + seed)
        back = self._sample(back_p, BACK_COUNT, BACK_MIN, seed=9500 + seed)
        return Ticket(front=front, back=back)
