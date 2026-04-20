"""
模型基类
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd

from ..config import TICKETS_PER_DRAW
from ..utils.numbers import validate_ticket


@dataclass
class Ticket:
    """
    单注投注号码
    """
    front: List[int]
    back: List[int]

    def valid(self) -> bool:
        return validate_ticket(self.front, self.back)


class BaseModel(ABC):
    """
    所有预测模型的基类，子类实现 _predict_one 即可
    """

    name: str = "base"

    @abstractmethod
    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        """
        根据历史数据生成一注号码

        @param history 按期号升序的历史 DataFrame，列：issue/front/back（均为 list）
        @param seed 随机种子，保证每张投注不同
        """
        raise NotImplementedError

    def predict(self, history: pd.DataFrame, n: int = TICKETS_PER_DRAW) -> List[Ticket]:
        """
        生成 n 注投注，保证每注合法且彼此不同

        @param history 历史数据
        @param n 投注数
        @returns 投注列表
        """
        tickets: List[Ticket] = []
        seed = 0
        seen: set[Tuple[Tuple[int, ...], Tuple[int, ...]]] = set()
        while len(tickets) < n and seed < 10_000:
            t = self._predict_one(history, seed)
            key = (tuple(sorted(t.front)), tuple(sorted(t.back)))
            if t.valid() and key not in seen:
                tickets.append(t)
                seen.add(key)
            seed += 1
        if len(tickets) < n:
            raise RuntimeError(f"{self.name} 模型生成投注失败")
        return tickets
