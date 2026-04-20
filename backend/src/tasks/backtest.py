"""
历史回测：在历史数据上模拟"如果我从某一期开始一直用该模型预测下一期，结果会怎样"
用于一次性补齐过往的模型表现曲线（而非等未来真实开奖）
"""
from __future__ import annotations

import argparse

from tqdm import tqdm

from ..config import MODELS, PRIZE_TABLE, TICKETS_PER_DRAW
from ..db import get_conn, init_db
from ..models import get_model
from ..utils.numbers import count_hits, encode
from .dataio import load_history


def run_backtest(start_idx: int = -200, force: bool = False) -> None:
    """
    对历史数据做滚动回测

    @param start_idx 起始索引（负数表示倒数第 N 期开始回测）
    @param force 是否覆盖已存在的预测与评估
    """
    init_db()
    history = load_history()
    n_total = len(history)
    if n_total < 100:
        raise RuntimeError("历史数据太少，无法回测")

    if start_idx < 0:
        start_idx = max(50, n_total + start_idx)
    start_idx = max(start_idx, 50)

    issues_to_test = history.iloc[start_idx:]
    print(f"回测：从期号 {issues_to_test.iloc[0]['issue']} 到 {issues_to_test.iloc[-1]['issue']}，共 {len(issues_to_test)} 期")

    with get_conn() as conn:
        for i, row in tqdm(
            list(enumerate(issues_to_test.itertuples(index=False))),
            desc="回测进度",
        ):
            real_issue = row.issue
            real_front = row.front
            real_back = row.back
            past = history.iloc[: start_idx + i]

            for name in MODELS:
                existing = conn.execute(
                    "SELECT 1 FROM predictions WHERE issue = ? AND model = ? LIMIT 1",
                    (real_issue, name),
                ).fetchone()
                if existing and not force:
                    continue
                if force:
                    conn.execute(
                        "DELETE FROM predictions WHERE issue = ? AND model = ?",
                        (real_issue, name),
                    )
                    conn.execute(
                        "DELETE FROM results WHERE issue = ? AND model = ?",
                        (real_issue, name),
                    )

                model = get_model(name)
                tickets = model.predict(past, n=TICKETS_PER_DRAW)
                for idx, t in enumerate(tickets):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO predictions
                          (issue, model, ticket_idx, front, back)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (real_issue, name, idx, encode(t.front), encode(t.back)),
                    )
                    fh, bh = count_hits(t.front, t.back, real_front, real_back)
                    level, amount = PRIZE_TABLE.get((fh, bh), (None, 0))
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO results
                          (issue, model, ticket_idx, front_hit, back_hit, prize_level, prize_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (real_issue, name, idx, fh, bh, level, amount),
                    )
            conn.commit()

    print("回测完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="大乐透模型历史回测")
    parser.add_argument(
        "--start",
        type=int,
        default=-200,
        help="起始索引；负数表示倒数第 N 期（默认 -200，即最近 200 期）",
    )
    parser.add_argument("--force", action="store_true", help="覆盖已有记录")
    args = parser.parse_args()
    run_backtest(args.start, args.force)
