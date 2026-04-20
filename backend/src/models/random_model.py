"""
随机基线模型（对照组，任何模型长期命中率都该和它同数量级）
"""
import random

import pandas as pd

from ..config import BACK_COUNT, BACK_MAX, BACK_MIN, FRONT_COUNT, FRONT_MAX, FRONT_MIN
from .base import BaseModel, Ticket


class RandomModel(BaseModel):
    """
    纯随机抽号，用作其他模型的对照基线
    """

    name = "random"

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        rng = random.Random(f"random-{len(history)}-{seed}")
        front = rng.sample(range(FRONT_MIN, FRONT_MAX + 1), FRONT_COUNT)
        back = rng.sample(range(BACK_MIN, BACK_MAX + 1), BACK_COUNT)
        return Ticket(front=front, back=back)
