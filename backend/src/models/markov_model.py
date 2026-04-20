"""
马尔可夫链模型：基于"上一期号码 → 下一期号码"的转移概率预测
用于验证"号码有惯性/记忆"这个说法
"""
import random

import numpy as np
import pandas as pd

from ..config import BACK_COUNT, BACK_MAX, BACK_MIN, FRONT_COUNT, FRONT_MAX, FRONT_MIN
from .base import BaseModel, Ticket


class MarkovModel(BaseModel):
    """
    构建一阶马尔可夫转移矩阵 P[i,j]：上一期出现 i 时，下一期出现 j 的概率
    """

    name = "markov"

    def _build_transition(self, history: pd.DataFrame, is_front: bool) -> np.ndarray:
        """
        构建转移矩阵（含拉普拉斯平滑）

        @param history 历史数据
        @param is_front 是否为前区
        @returns (N, N) 概率矩阵，每行归一化
        """
        lo, hi = (FRONT_MIN, FRONT_MAX) if is_front else (BACK_MIN, BACK_MAX)
        size = hi - lo + 1
        mat = np.ones((size, size), dtype=np.float64)

        key = "front" if is_front else "back"
        rows = list(history[key])
        for prev, curr in zip(rows[:-1], rows[1:]):
            for p in prev:
                for c in curr:
                    mat[p - lo, c - lo] += 1
        mat /= mat.sum(axis=1, keepdims=True)
        return mat

    @staticmethod
    def _sample_from_probs(probs: np.ndarray, k: int, lo: int, rng: random.Random) -> list:
        """
        从概率向量中不放回抽样 k 个号码

        @param probs 概率向量（非负，和为 1）
        @param k 抽样数
        @param lo 号码最小值（用于从索引映射回实际号码）
        """
        idxs: list = []
        p = probs.copy()
        for _ in range(k):
            p = p / p.sum() if p.sum() > 0 else np.ones_like(p) / len(p)
            pick = rng.random()
            acc = 0.0
            for i, pi in enumerate(p):
                acc += pi
                if acc >= pick:
                    idxs.append(i)
                    p[i] = 0
                    break
        return [i + lo for i in idxs]

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        rng = random.Random(f"markov-{len(history)}-{seed}")

        front_mat = self._build_transition(history, is_front=True)
        back_mat = self._build_transition(history, is_front=False)

        last = history.iloc[-1]
        last_front = last["front"]
        last_back = last["back"]

        front_probs = np.zeros(FRONT_MAX - FRONT_MIN + 1)
        for p in last_front:
            front_probs += front_mat[p - FRONT_MIN]
        front_probs /= len(last_front)

        back_probs = np.zeros(BACK_MAX - BACK_MIN + 1)
        for p in last_back:
            back_probs += back_mat[p - BACK_MIN]
        back_probs /= len(last_back)

        front = self._sample_from_probs(front_probs, FRONT_COUNT, FRONT_MIN, rng)
        back = self._sample_from_probs(back_probs, BACK_COUNT, BACK_MIN, rng)
        return Ticket(front=front, back=back)
