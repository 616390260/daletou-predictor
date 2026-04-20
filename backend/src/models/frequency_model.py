"""
频率统计模型：基于号码历史出现频次进行加权随机抽样
实质上是在验证"热号理论"是否成立
"""
import random
from collections import Counter

import pandas as pd

from ..config import BACK_COUNT, BACK_MAX, BACK_MIN, FRONT_COUNT, FRONT_MAX, FRONT_MIN
from .base import BaseModel, Ticket


class FrequencyModel(BaseModel):
    """
    使用加权抽样：出现频率越高的号码被抽中概率越高
    支持衰减系数，让近期数据权重更大
    """

    name = "frequency"

    def __init__(self, recent_window: int = 300, decay: float = 0.995) -> None:
        """
        @param recent_window 近期窗口大小（只看最近 N 期，太久之前不考虑）
        @param decay 时间衰减因子，越近的期数权重越高
        """
        self.recent_window = recent_window
        self.decay = decay

    def _build_weights(self, history: pd.DataFrame) -> tuple[dict, dict]:
        """
        基于历史构造前区和后区的权重字典

        @returns (front_weights, back_weights)
        """
        recent = history.tail(self.recent_window)
        front_counter: Counter[int] = Counter()
        back_counter: Counter[int] = Counter()
        total = len(recent)
        for idx, row in enumerate(recent.itertuples(index=False)):
            weight = self.decay ** (total - idx - 1)
            for n in row.front:
                front_counter[n] += weight
            for n in row.back:
                back_counter[n] += weight

        front_weights = {n: front_counter.get(n, 0.5) + 0.5 for n in range(FRONT_MIN, FRONT_MAX + 1)}
        back_weights = {n: back_counter.get(n, 0.5) + 0.5 for n in range(BACK_MIN, BACK_MAX + 1)}
        return front_weights, back_weights

    @staticmethod
    def _weighted_sample(weights: dict, k: int, rng: random.Random) -> list:
        """
        不放回加权抽样

        @param weights 号码 → 权重
        @param k 需要抽取数量
        @param rng 随机源
        """
        pool = list(weights.keys())
        w = list(weights.values())
        chosen: list = []
        for _ in range(k):
            total = sum(w)
            pick = rng.uniform(0, total)
            acc = 0.0
            for i, wi in enumerate(w):
                acc += wi
                if acc >= pick:
                    chosen.append(pool[i])
                    w[i] = 0
                    break
        return chosen

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        rng = random.Random(f"freq-{len(history)}-{seed}")
        front_w, back_w = self._build_weights(history)
        front = self._weighted_sample(front_w, FRONT_COUNT, rng)
        back = self._weighted_sample(back_w, BACK_COUNT, rng)
        return Ticket(front=front, back=back)
