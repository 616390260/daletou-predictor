"""
预测任务：读取历史数据 → 对每个模型生成 4 注投注 → 入库 predictions 表
"""
from __future__ import annotations

import argparse

from ..config import MODEL_LABELS, MODELS, TICKETS_PER_DRAW
from ..db import get_conn, init_db
from ..models import get_model
from ..utils.notifier import notify
from ..utils.numbers import decode, encode
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


def run_predict(target_issue: str | None = None, force: bool = False) -> None:
    """
    生成下一期预测

    @param target_issue 要预测的期号，默认自动推断为最新一期 +1
    @param force 是否覆盖已有预测
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

    _send_predict_notification(issue)


def _send_predict_notification(issue: str) -> None:
    """
    把本期全部模型的预测号码组装成 Markdown 发微信
    """
    lines = [f"# 🎰 大乐透 第 {issue} 期预测", ""]
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT model, ticket_idx, front, back
            FROM predictions WHERE issue = ?
            ORDER BY model, ticket_idx
            """,
            (issue,),
        ).fetchall()

    buckets: dict[str, list] = {}
    for r in rows:
        buckets.setdefault(r["model"], []).append(r)

    for model in MODELS:
        if model not in buckets:
            continue
        lines.append(f"### {MODEL_LABELS.get(model, model)}")
        for r in sorted(buckets[model], key=lambda x: x["ticket_idx"]):
            f_str = " ".join(f"`{n:02d}`" for n in decode(r["front"]))
            b_str = " ".join(f"`{n:02d}`" for n in decode(r["back"]))
            lines.append(f"- 注{r['ticket_idx'] + 1}：前 {f_str} | 后 {b_str}")
        lines.append("")

    lines.append("---")
    lines.append("📊 本预测仅供算法研究，理性购彩。")

    notify(f"大乐透 {issue} 期预测", "\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成大乐透下一期预测")
    parser.add_argument("--issue", help="指定期号，默认自动 +1")
    parser.add_argument("--force", action="store_true", help="覆盖已有预测")
    args = parser.parse_args()
    run_predict(args.issue, args.force)
