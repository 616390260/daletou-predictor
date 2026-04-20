"""
遗传算法模型：把"一注号码"当作个体，适应度 = 该注在历史上的回本率

思路：
1. 随机生成种群
2. 适应度 = 若历史每一期都买这注号，总中奖金 ÷ 总花费
3. 交叉 + 变异生成下一代
4. 迭代 N 代后取 top-K 个体作为推荐投注
"""
from __future__ import annotations

import random
from typing import List

import pandas as pd

from ..config import (
    BACK_COUNT,
    BACK_MAX,
    BACK_MIN,
    FRONT_COUNT,
    FRONT_MAX,
    FRONT_MIN,
    PRIZE_TABLE,
    TICKET_PRICE,
)
from ..utils.numbers import count_hits
from .base import BaseModel, Ticket

POP_SIZE = 60
GENERATIONS = 40
ELITE = 10
MUTATION_RATE = 0.15


def _fitness(ind: Ticket, history: pd.DataFrame) -> float:
    """
    个体适应度 = 若全部历史期都买这一注的总收益 / 总花费

    @param ind 个体（一注号码）
    @param history 历史数据
    """
    total_prize = 0
    n = len(history)
    for row in history.itertuples(index=False):
        fh, bh = count_hits(ind.front, ind.back, row.front, row.back)
        prize = PRIZE_TABLE.get((fh, bh), (None, 0))[1]
        total_prize += prize
    cost = max(n * TICKET_PRICE, 1)
    return total_prize / cost


def _random_individual(rng: random.Random) -> Ticket:
    """
    随机生成一个合法个体
    """
    front = rng.sample(range(FRONT_MIN, FRONT_MAX + 1), FRONT_COUNT)
    back = rng.sample(range(BACK_MIN, BACK_MAX + 1), BACK_COUNT)
    return Ticket(front=front, back=back)


def _crossover(a: Ticket, b: Ticket, rng: random.Random) -> Ticket:
    """
    交叉：前后区各独立随机选父方号码，并补足
    """
    def _mix(xs: List[int], ys: List[int], k: int, lo: int, hi: int) -> List[int]:
        pool = list(set(xs) | set(ys))
        rng.shuffle(pool)
        chosen = pool[:k]
        while len(chosen) < k:
            c = rng.randint(lo, hi)
            if c not in chosen:
                chosen.append(c)
        return chosen

    front = _mix(a.front, b.front, FRONT_COUNT, FRONT_MIN, FRONT_MAX)
    back = _mix(a.back, b.back, BACK_COUNT, BACK_MIN, BACK_MAX)
    return Ticket(front=front, back=back)


def _mutate(ind: Ticket, rng: random.Random) -> Ticket:
    """
    变异：以一定概率替换一个前区号或后区号
    """
    front = list(ind.front)
    back = list(ind.back)
    if rng.random() < MUTATION_RATE:
        i = rng.randrange(FRONT_COUNT)
        while True:
            n = rng.randint(FRONT_MIN, FRONT_MAX)
            if n not in front:
                front[i] = n
                break
    if rng.random() < MUTATION_RATE:
        i = rng.randrange(BACK_COUNT)
        while True:
            n = rng.randint(BACK_MIN, BACK_MAX)
            if n not in back:
                back[i] = n
                break
    return Ticket(front=front, back=back)


class GeneticModel(BaseModel):
    """
    遗传算法模型。适应度较慢，用最近窗口期加速。
    """

    name = "genetic"

    def __init__(self, recent_window: int = 400) -> None:
        self.recent_window = recent_window
        self._cache: List[Ticket] | None = None
        self._cache_key: int = -1

    def _evolve(self, history: pd.DataFrame) -> List[Ticket]:
        """
        跑一次完整的 GA，返回精英种群
        """
        rng = random.Random(f"ga-{len(history)}")
        window = history.tail(self.recent_window)
        population = [_random_individual(rng) for _ in range(POP_SIZE)]

        for _ in range(GENERATIONS):
            scored = [(ind, _fitness(ind, window)) for ind in population]
            scored.sort(key=lambda x: x[1], reverse=True)
            elites = [s[0] for s in scored[:ELITE]]
            new_pop = list(elites)
            while len(new_pop) < POP_SIZE:
                a, b = rng.sample(elites, 2)
                child = _mutate(_crossover(a, b, rng), rng)
                new_pop.append(child)
            population = new_pop

        scored = [(ind, _fitness(ind, window)) for ind in population]
        scored.sort(key=lambda x: x[1], reverse=True)

        seen: set[tuple] = set()
        unique: List[Ticket] = []
        for ind, _ in scored:
            key = (tuple(sorted(ind.front)), tuple(sorted(ind.back)))
            if key in seen:
                continue
            seen.add(key)
            unique.append(ind)
            if len(unique) >= ELITE:
                break

        rng = random.Random(f"ga-fill-{len(history)}")
        while len(unique) < ELITE:
            ind = _random_individual(rng)
            key = (tuple(sorted(ind.front)), tuple(sorted(ind.back)))
            if key not in seen:
                seen.add(key)
                unique.append(ind)
        return unique

    def _predict_one(self, history: pd.DataFrame, seed: int) -> Ticket:
        if self._cache is None or self._cache_key != len(history):
            self._cache = self._evolve(history)
            self._cache_key = len(history)
        return self._cache[seed % len(self._cache)]
