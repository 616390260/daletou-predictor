"""
贝叶斯模型：Beta-Bernoulli 模型 · 每个号码独立建模

先验 Beta(α, β)，每期观测一次是否出现 → 更新 posterior。
因为大乐透是真随机（均匀），理论 posterior 会收敛到 先验 ≈ 5/35（前区）或 2/12（后区）。
该模型的意义在于：
- 它是"最规范的频率学派"建模方法，有完整的不确定性表达
- 它的表现应当与随机基线无显著差异，用来戳破"冷热号"错觉

每个号码 i 的 posterior = Beta(α + 出现次数, β + 未出现次数)
预测：按 posterior mean 加权抽样
"""
import random
from typing import List

import numpy as np
import pandas as pd

from ..config import (
    BACK_COUNT,
    BACK_MAX,
    BACK_MIN,
    FRONT_COUNT,
    FRONT_MAX,
    FRONT_MIN,
)
from .base import BaseModel, Ticket


class BayesianModel(BaseModel):
    """
    Beta-Bernoulli 贝叶斯模型

    参数：
    - prior_strength：先验"虚拟观测数"；越大越贴近均匀先验
    - time_decay：时间衰减，近期观测权重更大
    """

    name = "bayesian"

    def __init__(self, prior_strength: float = 50.0, time_decay: float = 0.999) -> None:
        self.prior_strength = prior_strength
        self.time_decay = time_decay

    def _posterior_mean(self, history: pd.DataFrame, is_front: bool) -> np.ndarray:
        """
        计算 posterior mean 向量

        @param is_front 是否前区
        @returns 号码概率向量
        """
        lo, hi = (FRONT_MIN, FRONT_MAX) if is_front else (BACK_MIN, BACK_MAX)
        k = FRONT_COUNT if is_front else BACK_COUNT
        size = hi - lo + 1
        key = "front" if is_front else "back"

        prior_alpha = self.prior_strength * (k / size)
        prior_beta = self.prior_strength * (1 - k / size)

        success = np.zeros(size, dtype=np.float64)
        total = 0.0
        n = len(history)
        for idx, row in enumerate(history.itertuples(index=False)):
            w = self.time_decay ** (n - idx - 1)
            total += w
            for num in getattr(row, key):
                success[num - lo] += w

        alpha = prior_alpha + success
        beta = prior_beta + (total - success)
        return alpha / (alpha + beta)

    @staticmethod
    def _sample(probs: np.ndarray, k: int, lo: int, seed: int) -> List[int]:
        """
        按概率向量不放回抽样
        """
        rng = random.Random(seed)
        p = probs.astype(np.float64).copy()
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
        front_p = self._posterior_mean(history, is_front=True)
        back_p = self._posterior_mean(history, is_front=False)
        front = self._sample(front_p, FRONT_COUNT, FRONT_MIN, seed=7000 + seed)
        back = self._sample(back_p, BACK_COUNT, BACK_MIN, seed=8000 + seed)
        return Ticket(front=front, back=back)
