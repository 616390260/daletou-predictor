"""
集成模型：读取其他所有模型对下一期的预测，
按各模型"历史命中率"加权投票，产出共识号码

→ 这是一个 meta-learning 思路：让表现好的模型话语权更高
→ 无需独立训练，只依赖其他模型的预测与历史评估结果
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import pandas as pd

from ..config import (
    BACK_COUNT,
    BACK_MAX,
    BACK_MIN,
    FRONT_COUNT,
    FRONT_MAX,
    FRONT_MIN,
)
from ..db import get_conn
from ..utils.numbers import decode
from .base import BaseModel, Ticket

OTHER_MODELS = ["random", "frequency", "markov", "lstm", "genetic"]


def _model_weights() -> Dict[str, float]:
    """
    查询数据库算每个模型的历史命中率作为权重
    无历史记录时回落为 1.0（均等）
    """
    weights: Dict[str, float] = {name: 1.0 for name in OTHER_MODELS}
    try:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT model,
                       COUNT(*)                                        AS total,
                       SUM(CASE WHEN prize_amount > 0 THEN 1 ELSE 0 END) AS wins
                FROM results GROUP BY model
                """
            ).fetchall()
        for r in rows:
            if r["model"] not in OTHER_MODELS or r["total"] == 0:
                continue
            rate = (r["wins"] or 0) / r["total"]
            weights[r["model"]] = max(0.1, 1.0 + 3.0 * rate)
    except Exception:
        pass
    return weights


def _fetch_other_predictions(issue: str) -> Dict[str, List[Tuple[List[int], List[int]]]]:
    """
    读取指定期号下其他模型的全部预测号码

    @param issue 期号
    @returns {模型名: [(front, back), ...]}
    """
    out: Dict[str, List[Tuple[List[int], List[int]]]] = defaultdict(list)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT model, front, back FROM predictions WHERE issue = ? AND model != 'ensemble'",
            (issue,),
        ).fetchall()
    for r in rows:
        out[r["model"]].append((decode(r["front"]), decode(r["back"])))
    return out


class EnsembleModel(BaseModel):
    """
    集成模型：加权投票
    """

    name = "ensemble"

    def __init__(self, target_issue: str | None = None) -> None:
        """
        @param target_issue 目标期号；预测任务里需要在运行前把其它模型都跑完
        """
        self.target_issue = target_issue
        self._cache: List[Ticket] | None = None

    def _build_ensemble_tickets(self, history: pd.DataFrame) -> List[Ticket]:
        """
        根据其他模型对同一期的预测进行加权投票，构造 4 张集成票
        """
        import random

        if not self.target_issue:
            raise RuntimeError("EnsembleModel 需要先设置 target_issue")

        preds = _fetch_other_predictions(self.target_issue)
        weights = _model_weights()

        front_votes: Dict[int, float] = {n: 0.0 for n in range(FRONT_MIN, FRONT_MAX + 1)}
        back_votes: Dict[int, float] = {n: 0.0 for n in range(BACK_MIN, BACK_MAX + 1)}

        if not preds:
            print("[ensemble] 暂无其他模型预测，回退到均匀投票")
            for n in front_votes:
                front_votes[n] = 1.0
            for n in back_votes:
                back_votes[n] = 1.0
        else:
            for model_name, tickets in preds.items():
                w = weights.get(model_name, 1.0)
                for front, back in tickets:
                    for n in front:
                        front_votes[n] += w
                    for n in back:
                        back_votes[n] += w

        def _softsample(scores: Dict[int, float], k: int, seed: int) -> List[int]:
            rng = random.Random(seed)
            items = list(scores.items())
            items.sort(key=lambda x: x[1], reverse=True)
            top_candidates = items[: max(k * 2, 12)]
            pool = [n for n, _ in top_candidates]
            weights_pool = [max(s, 1e-3) for _, s in top_candidates]
            picked: List[int] = []
            available = list(pool)
            available_w = list(weights_pool)
            for _ in range(k):
                total = sum(available_w)
                pick = rng.uniform(0, total)
                acc = 0.0
                for i, wi in enumerate(available_w):
                    acc += wi
                    if acc >= pick:
                        picked.append(available[i])
                        available.pop(i)
                        available_w.pop(i)
                        break
            return picked

        tickets: List[Ticket] = []
        seen = set()
        attempt = 0
        while len(tickets) < 4 and attempt < 50:
            front = _softsample(front_votes, FRONT_COUNT, seed=attempt * 7 + 1)
            back = _softsample(back_votes, BACK_COUNT, seed=attempt * 7 + 2)
            key = (tuple(sorted(front)), tuple(sorted(back)))
            if key not in seen:
                seen.add(key)
                tickets.append(Ticket(front=front, back=back))
            attempt += 1
        return tickets

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        if self._cache is None:
            self._cache = self._build_ensemble_tickets(history)
        return self._cache[seed % len(self._cache)]
