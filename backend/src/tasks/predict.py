"""
预测任务：读取历史数据 → 对每个模型生成 TICKETS_PER_DRAW 注投注 → 入库 predictions 表
"""
from __future__ import annotations

import argparse

from datetime import datetime, timedelta, timezone

from ..config import DATA_DIR, MODELS, TICKETS_PER_DRAW
from ..db import get_conn, init_db
from ..models import get_model
from ..utils.notifier import notify, repo_raw_url
from ..utils.numbers import encode
from .dataio import load_history, next_issue_guess


def _existing_models_for_issue(issue: str) -> set[str]:
    """
    查询某一期已经有哪些模型生成过预测（防止重复生成）
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT model FROM predictions WHERE issue = ?", (issue,)
        ).fetchall()
    return {r["model"] for r in rows}


def run_predict(target_issue: str | None = None, force: bool = False,
                notify_on_done: bool = True) -> str:
    """
    生成下一期预测

    @param target_issue 要预测的期号，默认自动推断为最新一期 +1
    @param force 是否覆盖已有预测
    @param notify_on_done 完成后是否立即推送微信
    @returns 本次预测的期号
    """
    init_db()
    history = load_history()
    if len(history) < 50:
        raise RuntimeError("历史数据不足，请先运行爬虫 fetch_history.py")

    latest_issue = history.iloc[-1]["issue"]
    issue = target_issue or next_issue_guess(latest_issue)
    existing = _existing_models_for_issue(issue)

    print(f"为期号 {issue} 生成预测（已存在: {sorted(existing) or '无'}）")

    with get_conn() as conn:
        for name in MODELS:
            if name in existing and not force:
                print(f"  {name}: 已存在，跳过")
                continue
            if force:
                conn.execute(
                    "DELETE FROM predictions WHERE issue = ? AND model = ?",
                    (issue, name),
                )
                conn.commit()
            print(f"  {name}: 生成中...")
            kwargs = {"target_issue": issue} if name == "ensemble" else {}
            model = get_model(name, **kwargs)
            tickets = model.predict(history, n=TICKETS_PER_DRAW)
            for idx, t in enumerate(tickets):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO predictions
                      (issue, model, ticket_idx, front, back)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (issue, name, idx, encode(t.front), encode(t.back)),
                )
            conn.commit()
            for idx, t in enumerate(tickets):
                print(f"    注{idx + 1}: 前 {encode(t.front)}  后 {encode(t.back)}")

    if notify_on_done:
        _send_predict_notification(issue)
    return issue


def notify_predict(issue: str) -> None:
    """
    仅推送指定期号的预测通知（不重新生成预测）
    """
    _send_predict_notification(issue)


def _next_draw_text(issue: str) -> str:
    """
    根据期号猜下一期开奖时间（周一/三/六 20:30 北京时间）

    @param issue 预测期号
    @returns 形如 "2026-04-22 周三 20:30" 的字符串
    """
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    for i in range(14):
        d = now + timedelta(days=i)
        if d.weekday() in (0, 2, 5):
            target = d.replace(hour=20, minute=30, second=0, microsecond=0)
            if target > now:
                wd = "一二三四五六日"[d.weekday()]
                return target.strftime(f"%Y-%m-%d 周{wd} %H:%M")
    return ""


def _count_predictions(issue: str) -> tuple[int, int]:
    """
    统计本期预测的模型数量与总注数

    @returns (模型数, 总注数)
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT model) AS m, COUNT(*) AS n "
            "FROM predictions WHERE issue = ?",
            (issue,),
        ).fetchone()
    return (row["m"] or 0, row["n"] or 0)


def _send_predict_notification(issue: str) -> None:
    """
    推送本期预测：以汇总大图为主，文字极简
    """
    n_models, n_tickets = _count_predictions(issue)
    draw_at = _next_draw_text(issue)

    lines: list[str] = []
    summary_img = DATA_DIR / "img" / f"predictions_{issue}.png"
    if summary_img.exists():
        url = repo_raw_url(f"data/img/predictions_{issue}.png")
        if url:
            lines.append(f"![predictions]({url})")
            lines.append("")

    lines.append("## 本期预测")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    lines.append(f"| 期号 | **{issue}** |")
    if draw_at:
        lines.append(f"| 开奖 | {draw_at} |")
    lines.append(f"| 模型 | {n_models} 个 |")
    lines.append(f"| 注数 | {n_tickets} 注 |")
    lines.append("")

    trend_img = DATA_DIR / "img" / "hit_trend.png"
    if trend_img.exists():
        url = repo_raw_url("data/img/hit_trend.png")
        if url:
            lines.append("## 历史命中率")
            lines.append(f"![hit_trend]({url})")
            lines.append("")

    lines.append("---")
    lines.append("> 算法研究项目，仅供学习，请理性购彩 🙏")

    title = f"🎰 {issue} 期预测 · {n_tickets} 注"
    notify(title, "\n".join(lines))


if __name__ == "__main__":
    import os

    parser = argparse.ArgumentParser(description="生成大乐透下一期预测")
    parser.add_argument("--issue", help="指定期号，默认自动 +1")
    parser.add_argument("--force", action="store_true", help="覆盖已有预测")
    parser.add_argument("--no-notify", action="store_true",
                        help="只入库不推送（供 workflow 分步使用）")
    parser.add_argument("--notify-only", action="store_true",
                        help="不重新预测，仅推送指定期号")
    parser.add_argument("--print-issue", action="store_true",
                        help="把本次预测的期号写入 GITHUB_OUTPUT / stdout")
    args = parser.parse_args()
    if args.notify_only:
        if not args.issue:
            raise SystemExit("--notify-only 需要同时指定 --issue")
        notify_predict(args.issue)
    else:
        issue = run_predict(args.issue, args.force,
                            notify_on_done=not args.no_notify)
        if args.print_issue:
            out = os.environ.get("GITHUB_OUTPUT")
            if out:
                with open(out, "a") as f:
                    f.write(f"issue={issue}\n")
            print(f"issue={issue}")
