"""
评估任务：对比已有预测 vs 已开奖结果 → 计算命中数、奖级、金额 → 入库 results 表
"""
from __future__ import annotations

import argparse

from ..config import DATA_DIR, MODEL_LABELS, MODELS, PRIZE_TABLE, TICKET_PRICE
from ..db import get_conn, init_db
from ..utils.notifier import notify, repo_raw_url
from ..utils.numbers import count_hits, decode


def evaluate_issue(issue: str) -> int:
    """
    评估单期所有模型的预测命中情况

    @param issue 期号
    @returns 本次评估的记录数
    """
    with get_conn() as conn:
        draw = conn.execute(
            "SELECT front, back FROM draws WHERE issue = ?", (issue,)
        ).fetchone()
        if draw is None:
            print(f"期号 {issue} 尚未开奖，跳过")
            return 0
        real_front = decode(draw["front"])
        real_back = decode(draw["back"])

        preds = conn.execute(
            "SELECT model, ticket_idx, front, back FROM predictions WHERE issue = ?",
            (issue,),
        ).fetchall()
        if not preds:
            print(f"期号 {issue} 无预测记录，跳过")
            return 0

        n = 0
        for p in preds:
            pf = decode(p["front"])
            pb = decode(p["back"])
            fh, bh = count_hits(pf, pb, real_front, real_back)
            level, amount = PRIZE_TABLE.get((fh, bh), (None, 0))
            conn.execute(
                """
                INSERT OR REPLACE INTO results
                  (issue, model, ticket_idx, front_hit, back_hit, prize_level, prize_amount)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (issue, p["model"], p["ticket_idx"], fh, bh, level, amount),
            )
            n += 1
        conn.commit()
    print(f"期号 {issue} 已评估 {n} 条预测")
    _send_evaluate_notification(issue)
    return n


def _send_evaluate_notification(issue: str) -> None:
    """
    生成本期开奖对照 + 各模型命中汇总，推送到微信
    """
    with get_conn() as conn:
        draw = conn.execute(
            "SELECT draw_date, front, back FROM draws WHERE issue = ?", (issue,)
        ).fetchone()
        if not draw:
            return
        rows = conn.execute(
            """
            SELECT model,
                   COUNT(*) AS tickets,
                   SUM(CASE WHEN prize_amount > 0 THEN 1 ELSE 0 END) AS wins,
                   SUM(prize_amount) AS prize,
                   MAX(front_hit) AS best_f,
                   MAX(back_hit) AS best_b
            FROM results WHERE issue = ?
            GROUP BY model
            """,
            (issue,),
        ).fetchall()

    real_front = " ".join(f"`{n:02d}`" for n in decode(draw["front"]))
    real_back = " ".join(f"`{n:02d}`" for n in decode(draw["back"]))

    lines = [
        f"# 📣 大乐透 第 {issue} 期开奖",
        f"**日期**：{draw['draw_date']}",
        f"**开奖号**：前 {real_front} | 后 {real_back}",
        "",
    ]

    # 引用已 commit 的号码球图（workflow 在此之前生成并 push）
    draw_img = DATA_DIR / "img" / f"draw_{issue}.png"
    if draw_img.exists():
        url = repo_raw_url(f"data/img/{draw_img.name}")
        if url:
            lines.append(f"![draw]({url})")
            lines.append("")

    lines.append("### 模型命中汇总")

    stat_map = {r["model"]: r for r in rows}
    total_cost_all = 0
    total_prize_all = 0

    for model in MODELS:
        r = stat_map.get(model)
        if not r:
            continue
        cost = (r["tickets"] or 0) * TICKET_PRICE
        prize = r["prize"] or 0
        total_cost_all += cost
        total_prize_all += prize
        emoji = "🎉" if prize > 0 else "⚪"
        lines.append(
            f"{emoji} **{MODEL_LABELS.get(model, model)}**："
            f"{r['wins']}/{r['tickets']} 注命中，"
            f"最佳前区 {r['best_f']}/后区 {r['best_b']}，"
            f"投入 ¥{cost} → 回报 ¥{prize}"
        )

    roi = (total_prize_all - total_cost_all) / total_cost_all if total_cost_all else 0
    lines += [
        "",
        f"**总计**：投入 ¥{total_cost_all}，回报 ¥{total_prize_all}，"
        f"ROI {roi * 100:.1f}%",
        "",
    ]

    trend_img = DATA_DIR / "img" / "hit_trend.png"
    if trend_img.exists():
        url = repo_raw_url("data/img/hit_trend.png")
        if url:
            lines.append("### 📈 累计命中率曲线")
            lines.append(f"![hit_trend]({url})")
            lines.append("")

    lines.append("---")
    lines.append("📈 详情见模型对比页。")
    notify(f"大乐透 {issue} 期开奖速递", "\n".join(lines))


def evaluate_all() -> int:
    """
    评估所有已开奖且有预测但未评估的期号
    """
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.issue
            FROM predictions p
            JOIN draws d ON p.issue = d.issue
            LEFT JOIN results r ON p.issue = r.issue AND p.model = r.model AND p.ticket_idx = r.ticket_idx
            WHERE r.id IS NULL
            ORDER BY p.issue ASC
            """
        ).fetchall()
    issues = [r["issue"] for r in rows]
    print(f"待评估期号 {len(issues)} 个")
    total = 0
    for issue in issues:
        total += evaluate_issue(issue)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="评估大乐透预测命中情况")
    parser.add_argument("--issue", help="仅评估指定期号，不指定则评估全部待评估期号")
    args = parser.parse_args()
    if args.issue:
        evaluate_issue(args.issue)
    else:
        evaluate_all()
