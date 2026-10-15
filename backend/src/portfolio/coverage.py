"""Exact winning union under uniform draws; no target outcome is an input."""
from __future__ import annotations

import itertools
import math

import numpy as np

VERSION = 'back-coverage-v1'


def _mask(numbers, size, count):
    values = list(numbers)
    if (len(values) != count or len(set(values)) != count
            or any(type(n) is not int or not 1 <= n <= size for n in values)):
        raise ValueError('Invalid ticket numbers')
    return sum(1 << (n - 1) for n in values)


class Coverage:
    """Count all winning draws for fixed front tickets, varying their back pairs.

    @param fronts One five-number front selection per ticket, at most twelve.
    @returns An exact integer evaluator, accounting for overlaps between tickets.
    """

    def __init__(self, fronts, front_max=35, back_max=12):
        if not 1 <= len(fronts) <= 12 or not 5 <= front_max <= 35 or not 2 <= back_max <= 12:
            raise ValueError('Invalid coverage dimensions')
        self.n, self.back_max = len(fronts), back_max
        masks = [_mask(f, front_max, 5) for f in fronts]
        counts = np.zeros(1 << self.n, dtype=np.int64)
        automatic = 0
        for draw in itertools.combinations(range(front_max), 5):
            mask = sum(1 << i for i in draw)
            hits = [(mask & ticket).bit_count() for ticket in masks]
            if max(hits) >= 3:
                automatic += 1
            else:
                counts[sum(1 << i for i, h in enumerate(hits) if h == 2)] += 1
        self.patterns = np.flatnonzero(counts)
        self.counts = counts[self.patterns]
        self.back_total = math.comb(back_max, 2)
        self.base = automatic * self.back_total
        self.total = math.comb(front_max, 5) * self.back_total
        self.pair_counts = np.asarray([math.comb(back_max - m.bit_count(), 2)
                                      if back_max - m.bit_count() >= 2 else 0
                                      for m in range(1 << back_max)])

    def count(self, backs):
        """@returns Number of full draws where at least one ticket wins any prize."""
        if len(backs) != self.n:
            raise ValueError('Front/back ticket count mismatch')
        masks = [_mask(b, self.back_max, 2) for b in backs]
        hot = np.zeros(len(self.patterns), dtype=np.int64)
        for i, mask in enumerate(masks):
            hot |= np.where(self.patterns & (1 << i), mask, 0)
        # With two front hits, any matching back number wins. Otherwise only
        # exact back pairs win; count their union outside those hot numbers.
        unique = np.unique(masks)
        back_wins = self.back_total - self.pair_counts[hot] + ((hot[:, None] & unique) == 0).sum(axis=1)
        return self.base + int(self.counts @ back_wins)


def optimize(tickets, front_max=35, back_max=12, rounds=3):
    """Deterministic coordinate ascent, accepting strict coverage improvements only.

    @returns Original/optimized exact counts and same-budget tickets; no global optimum claim.
    """
    evaluator = Coverage([t['front'] for t in tickets], front_max, back_max)
    backs = [list(t['back']) for t in tickets]
    original = best = evaluator.count(backs)
    pairs = list(itertools.combinations(range(1, back_max + 1), 2))
    for _ in range(rounds):
        changed = False
        for i in range(len(backs)):
            selected = backs[i]
            for pair in pairs:
                trial = backs.copy()
                trial[i] = pair
                score = evaluator.count(trial)
                if score > best:
                    best, selected = score, list(pair)
            if selected != backs[i]:
                backs[i], changed = selected, True
        if not changed:
            break
    return {'original_count': original, 'optimized_count': best, 'total_draws': evaluator.total,
            'tickets': [{**t, 'front': list(t['front']), 'back': b} for t, b in zip(tickets, backs)]}
