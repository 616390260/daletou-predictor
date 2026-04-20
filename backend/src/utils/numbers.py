"""
号码编解码工具
"""
from typing import Iterable, List, Tuple

from ..config import BACK_COUNT, BACK_MAX, BACK_MIN, FRONT_COUNT, FRONT_MAX, FRONT_MIN


def encode(nums: Iterable[int]) -> str:
    """
    号码列表 → 逗号分隔字符串（升序）

    @param nums 号码列表
    @returns 形如 "03,12,18,22,31" 的字符串
    """
    return ",".join(f"{n:02d}" for n in sorted(int(x) for x in nums))


def decode(s: str) -> List[int]:
    """
    字符串 → 号码列表

    @param s 形如 "03,12,18,22,31"
    @returns 整数列表
    """
    if not s:
        return []
    return [int(x) for x in s.split(",") if x.strip()]


def validate_ticket(front: List[int], back: List[int]) -> bool:
    """
    校验一注号码是否合法

    @param front 前区号码
    @param back 后区号码
    @returns 合法返回 True
    """
    if len(set(front)) != FRONT_COUNT:
        return False
    if len(set(back)) != BACK_COUNT:
        return False
    if not all(FRONT_MIN <= n <= FRONT_MAX for n in front):
        return False
    if not all(BACK_MIN <= n <= BACK_MAX for n in back):
        return False
    return True


def count_hits(
    pred_front: List[int],
    pred_back: List[int],
    real_front: List[int],
    real_back: List[int],
) -> Tuple[int, int]:
    """
    统计一注预测的前/后区命中数

    @returns (前区命中数, 后区命中数)
    """
    return (
        len(set(pred_front) & set(real_front)),
        len(set(pred_back) & set(real_back)),
    )
