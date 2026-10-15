"""Issue-aware estimates for basic single-ticket prizes."""
from __future__ import annotations

from ..config import PRIZE_TABLE

NEW_RULE_FIRST_ISSUE = "26014"
POOL_THRESHOLD = 800_000_000
PRIZE_RULE_SOURCE = "https://file.fjtc.com.cn/Attachment/2026-01/16/8f534265-b571-4e98-844d-061b31308be1.pdf"
PRIZE_ESTIMATE_NOTE = (
    "奖金与ROI均为估算：26013期及以前沿用旧奖表估算；26014期起采用七奖级规则，"
    "8亿元档位以前一期开奖后奖池近似。浮动奖沿用估算值，追加投注、派奖及限额赔付未纳入。"
)

_FIXED_PRIZES = {
    (5, 0): ("三等奖", 5000, 6666),
    (4, 2): ("三等奖", 5000, 6666),
    (4, 1): ("四等奖", 300, 380),
    (4, 0): ("五等奖", 150, 200),
    (3, 2): ("五等奖", 150, 200),
    (3, 1): ("六等奖", 15, 18),
    (2, 2): ("六等奖", 15, 18),
    (3, 0): ("七等奖", 5, 7),
    (2, 1): ("七等奖", 5, 7),
    (1, 2): ("七等奖", 5, 7),
    (0, 2): ("七等奖", 5, 7),
}


def prize_for_hits(issue: str, fh: int, bh: int, pool_before: int = 0) -> tuple[str | None, int]:
    """Estimate a basic ticket payout under the issue's published rule.

    @param issue Five-digit issue identifier.
    @param fh Number of matched front balls.
    @param bh Number of matched back balls.
    @param pool_before Previous draw's post-draw pool, used as an approximation.
    @returns Prize label and estimated payout in yuan; non-wins return (None, 0).
    """
    issue = str(issue)
    if len(issue) != 5 or not issue.isdigit():
        raise ValueError(f"Invalid issue: {issue!r}")
    if issue < NEW_RULE_FIRST_ISSUE or (fh, bh) in {(5, 2), (5, 1)}:
        return PRIZE_TABLE.get((fh, bh), (None, 0))
    fixed = _FIXED_PRIZES.get((fh, bh))
    if fixed is None:
        return None, 0
    level, low, high = fixed
    return level, high if (pool_before or 0) >= POOL_THRESHOLD else low


def previous_pool(conn, issue: str) -> int:
    """Read the immediately preceding draw's pool without looking ahead.

    @param conn SQLite connection.
    @param issue Target issue.
    @returns Previous post-draw pool; zero if no previous draw or missing data.
    """
    row = conn.execute(
        "SELECT pool FROM draws WHERE issue < ? ORDER BY issue DESC LIMIT 1", (str(issue),)
    ).fetchone()
    return int(row[0] or 0) if row else 0
