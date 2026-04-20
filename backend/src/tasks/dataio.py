"""
数据读取与期号推算工具
"""
import pandas as pd

from ..db import get_conn
from ..utils.numbers import decode


def load_history() -> pd.DataFrame:
    """
    加载全部历史开奖，按期号升序，front/back 解码为 list[int]

    @returns DataFrame 列：issue/draw_date/front/back
    """
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT issue, draw_date, front, back, sales, pool "
            "FROM draws ORDER BY issue ASC",
            conn,
        )
    if len(df) == 0:
        return df
    df["front"] = df["front"].apply(decode)
    df["back"] = df["back"].apply(decode)
    return df


def next_issue_guess(latest_issue: str) -> str:
    """
    根据当前最新一期期号推出下一期期号（简单 +1 规则）

    @param latest_issue 当前最新期号，如 "25045"
    @returns 下一期期号，如 "25046"
    """
    try:
        num = int(latest_issue) + 1
        return f"{num:05d}"
    except ValueError:
        return latest_issue + "_next"
