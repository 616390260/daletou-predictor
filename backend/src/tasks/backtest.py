"""
历史回测：在历史数据上模拟"如果我从某一期开始一直用该模型预测下一期，结果会怎样"
用于一次性补齐过往的模型表现曲线（而非等未来真实开奖）
"""
from __future__ import annotations

import argparse
import json
import time

from tqdm import tqdm

from ..config import (
    BACKTEST_MIN_START_INDEX,
    DATA_DIR,
    MODELS,
    TICKETS_PER_DRAW,
)
from ..db import get_conn, init_db
from ..models import get_model
from ..utils.numbers import count_hits, encode
from ..utils.prizes import previous_pool, prize_for_hits
from .dataio import load_history

STATE_FILE = DATA_DIR / ".backtest_state.json"


def _write_state(state: dict) -> None:
    """
    将回测进度状态写入磁盘，供 GitHub Actions 判断是否需要自动续跑

    @param state 状态字典
    """
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_backtest(
    start_idx: int = -200,
    force: bool = False,
    only: list[str] | None = None,
    time_budget_seconds: float | None = None,
) -> dict:
    """
    对历史数据做滚动回测

    @param start_idx 起始索引（负数表示倒数第 N 期开始回测）
    @param force 是否覆盖已存在的预测与评估
    @param only 仅跑指定模型（None = 全部）
    @param time_budget_seconds 时间预算（秒），到点后在下一期边界主动停机；
                               None 表示不限制
    @returns 进度状态字典（含 done/processed/total/last_issue 等）
    """
    init_db()
    history = load_history()
    n_total = len(history)
    if n_total < 100:
        raise RuntimeError("历史数据太少，无法回测")

    if start_idx < 0:
        start_idx = max(BACKTEST_MIN_START_INDEX, n_total + start_idx)
    start_idx = max(start_idx, BACKTEST_MIN_START_INDEX)

    issues_to_test = history.iloc[start_idx:]
    total = len(issues_to_test)
    active_models = [m for m in MODELS if (not only) or m in only]
    print(
        f"回测：从期号 {issues_to_test.iloc[0]['issue']} 到 "
        f"{issues_to_test.iloc[-1]['issue']}，共 {total} 期；"
        f"模型：{active_models}"
    )
    if time_budget_seconds is not None:
        mins = time_budget_seconds / 60
        print(f"[time-budget] 本轮最多跑 {time_budget_seconds:.0f}s（≈ {mins:.1f} min），到点主动停机")

    t_start = time.monotonic()
    processed = 0
    skipped_draws = 0
    last_issue: str | None = None
    stopped_early = False

    with get_conn() as conn:
        for i, row in tqdm(
            list(enumerate(issues_to_test.itertuples(index=False))),
            desc="回测进度",
        ):
            real_issue = row.issue
            real_front = row.front
            real_back = row.back
            past = history.iloc[: start_idx + i]
            pool_before = previous_pool(conn, real_issue)

            did_any_work = False
            for name in active_models:
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

                kwargs = {"target_issue": real_issue} if name == "ensemble" else {}
                model = get_model(name, **kwargs)
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
                    level, amount = prize_for_hits(real_issue, fh, bh, pool_before)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO results
                          (issue, model, ticket_idx, front_hit, back_hit, prize_level, prize_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (real_issue, name, idx, fh, bh, level, amount),
                    )
                did_any_work = True

            conn.commit()
            last_issue = real_issue
            processed += 1
            if not did_any_work:
                skipped_draws += 1

            if time_budget_seconds is not None:
                elapsed = time.monotonic() - t_start
                if elapsed >= time_budget_seconds:
                    stopped_early = True
                    print(
                        f"\n[time-budget] 已运行 {elapsed:.0f}s 达到预算，"
                        f"主动停机；本轮处理 {processed}/{total} 期"
                        f"（其中 {skipped_draws} 期已有记录被跳过）"
                    )
                    break

    done = (not stopped_early) and (processed >= total)
    state = {
        "done": done,
        "stopped_early": stopped_early,
        "processed": processed,
        "total": total,
        "skipped_draws_this_run": skipped_draws,
        "last_issue": last_issue,
        "start_idx": start_idx,
        "models": active_models,
        "elapsed_seconds": round(time.monotonic() - t_start, 1),
    }
    _write_state(state)

    if done:
        print(f"回测完成：共处理 {processed} 期，状态文件 {STATE_FILE.name}")
    else:
        print(
            f"回测未完成（stopped_early={stopped_early}），"
            f"已处理 {processed}/{total}，下一轮从同一 start 继续即可自动跳过已有记录"
        )
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="大乐透模型历史回测")
    parser.add_argument(
        "--start",
        type=int,
        default=-200,
        help=(
            "起始索引（0-based 行号）；负数表示倒数第 N 期。"
            f" 小于 {BACKTEST_MIN_START_INDEX} 时会被抬到该值（与序列模型 WINDOW+1 对齐，≈全库最早可评估点）"
        ),
    )
    parser.add_argument("--force", action="store_true", help="覆盖已有记录")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="仅跑指定模型（逗号分隔），例如 random,frequency,bayesian,markov,genetic",
    )
    parser.add_argument(
        "--time-budget-seconds",
        type=float,
        default=None,
        help="本轮最多运行的秒数；到点后在下一期边界主动停机，不触发异常退出（用于 GitHub Actions 分段续跑）",
    )
    args = parser.parse_args()
    only = [x.strip() for x in args.only.split(",") if x.strip()] or None
    run_backtest(
        args.start,
        args.force,
        only=only,
        time_budget_seconds=args.time_budget_seconds,
    )
