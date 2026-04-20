"""
评估任务：对比已有预测 vs 已开奖结果 → 计算命中数、奖级、金额 → 入库 results 表
"""
from __future__ import annotations

import argparse

from ..config import DATA_DIR, MODEL_LABELS, MODELS, PRIZE_TABLE, TICKET_PRICE
from ..db import get_conn, init_db
from ..utils.notifier import notify, repo_raw_url
from ..utils.numbers import count_hits, decode


def evaluate_issue(issue: str, notify_on_done: bool = True) -> int:
    """
    评估单期所有模型的预测命中情况

    @param issue 期号
    @param notify_on_done 评估完成后是否立即推送微信
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
    if notify_on_done:
        _send_evaluate_notification(issue)
    return n


def notify_evaluate(issue: str) -> None:
    """
    仅推送指定期号的开奖通知（不重新评估）
    """
    _send_evaluate_notification(issue)


def _send_evaluate_notification(issue: str) -> None:
    """
    推送开奖速递：开奖号球图 + 命中汇总表 + 趋势图
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

    lines: list[str] = []

    eval_img = DATA_DIR / "img" / f"evaluate_{issue}.png"
    draw_img = DATA_DIR / "img" / f"draw_{issue}.png"
    if eval_img.exists():
        url = repo_raw_url(f"data/img/{eval_img.name}")
        if url:
            lines.append(f"![evaluate]({url})")
            lines.append("")
    elif draw_img.exists():
        url = repo_raw_url(f"data/img/{draw_img.name}")
        if url:
            lines.append(f"![draw]({url})")
            lines.append("")

    lines.append("## 命中汇总")
    lines.append("")
    lines.append("| 模型 | 命中 | 最佳 | 投入 | 回报 | ROI |")
    lines.append("| --- | :-: | :-: | -: | -: | -: |")

    stat_map = {r["model"]: r for r in rows}
    total_cost_all = 0
    total_prize_all = 0
    hit_models: list[str] = []

    for model in MODELS:
        r = stat_map.get(model)
        if not r:
            continue
        cost = (r["tickets"] or 0) * TICKET_PRICE
        prize = r["prize"] or 0
        total_cost_all += cost
        total_prize_all += prize
        roi_m = (prize - cost) / cost * 100 if cost else 0
        if prize > 0:
            hit_models.append(MODEL_LABELS.get(model, model))
        label = MODEL_LABELS.get(model, model)
        tag = "🎉" if prize > 0 else "·"
        lines.append(
            f"| {tag} {label} "
            f"| {r['wins']}/{r['tickets']} "
            f"| {r['best_f']}+{r['best_b']} "
            f"| ¥{cost} "
            f"| ¥{prize} "
            f"| {roi_m:+.0f}% |"
        )

    roi = (total_prize_all - total_cost_all) / total_cost_all if total_cost_all else 0
    lines.append("")
    lines.append("## 本期总计")
    lines.append("")
    lines.append(f"- 总投入：**¥{total_cost_all}**")
    lines.append(f"- 总回报：**¥{total_prize_all}**")
    lines.append(f"- 本期 ROI：**{roi * 100:+.1f}%**")
    if hit_models:
        lines.append(f"- 中奖模型：{'、'.join(hit_models)}")
    lines.append("")

    trend_img = DATA_DIR / "img" / "hit_trend.png"
    if trend_img.exists():
        url = repo_raw_url("data/img/hit_trend.png")
        if url:
            lines.append("## 累计命中率")
            lines.append(f"![hit_trend]({url})")
            lines.append("")

    lines.append("---")
    lines.append("> 算法研究项目，仅供学习，请理性购彩 🙏")

    if hit_models:
        title = f"🎉 {issue} 期中奖 · ROI {roi * 100:+.0f}%"
    else:
        title = f"📣 {issue} 期开奖 · ROI {roi * 100:+.0f}%"
    notify(title, "\n".join(lines))


def evaluate_all(notify_on_done: bool = True) -> list[str]:
    """
    评估所有已开奖且有预测但未评估的期号

    @param notify_on_done 每期是否推送微信
    @returns 本次成功评估的期号列表
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
    done: list[str] = []
    for issue in issues:
        if evaluate_issue(issue, notify_on_done=notify_on_done) > 0:
            done.append(issue)
    return done


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="评估大乐透预测命中情况")
    parser.add_argument("--issue", help="仅评估指定期号，不指定则评估全部待评估期号")
    parser.add_argument("--no-notify", action="store_true",
                        help="只入库不推送（供 workflow 分步使用）")
    parser.add_argument("--notify-only", action="store_true",
                        help="不重新评估，仅推送指定期号")
    parser.add_argument("--print-evaluated-issue", action="store_true",
                        help="把最新成功评估的期号打印到 stdout（供 workflow 读取）")
    args = parser.parse_args()

    if args.notify_only:
        if not args.issue:
            raise SystemExit("--notify-only 需要同时指定 --issue")
        notify_evaluate(args.issue)
    else:
        if args.issue:
            n = evaluate_issue(args.issue, notify_on_done=not args.no_notify)
            done = [args.issue] if n > 0 else []
        else:
            done = evaluate_all(notify_on_done=not args.no_notify)
        if args.print_evaluated_issue and done:
            import os
            latest = done[-1]
            out = os.environ.get("GITHUB_OUTPUT")
            if out:
                with open(out, "a") as f:
                    f.write(f"evaluated_issue={latest}\n")
            print(f"evaluated_issue={latest}")
