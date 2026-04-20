"""
图表生成器

用 matplotlib 绘制推送用的 PNG（深色主题），保存到 data/img/。
GitHub Actions 自动 commit 后，Server 酱 markdown 引用
https://raw.githubusercontent.com/<user>/<repo>/main/data/img/<name>.png
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # 非交互
import matplotlib.pyplot as plt

from ..config import DATA_DIR, MODELS, MODEL_LABELS, TICKET_PRICE
from ..db import get_conn
from ..utils.numbers import decode

IMG_DIR = DATA_DIR / "img"
IMG_DIR.mkdir(parents=True, exist_ok=True)

_MODEL_COLORS = {
    "random": "#71717a",
    "frequency": "#3b82f6",
    "bayesian": "#06b6d4",
    "markov": "#a855f7",
    "xgboost": "#84cc16",
    "lstm": "#ec4899",
    "transformer": "#f43f5e",
    "genetic": "#10b981",
    "ensemble": "#f59e0b",
}

_DARK_BG = "#0b0e14"
_CARD_BG = "#111827"
_TEXT = "#e5e7eb"
_MUTED = "#9ca3af"
_GRID = "#1f2937"

_EN_LABELS = {
    "random": "Random",
    "frequency": "Frequency",
    "bayesian": "Bayesian",
    "markov": "Markov",
    "xgboost": "XGBoost",
    "lstm": "LSTM",
    "transformer": "Transformer",
    "genetic": "Genetic",
    "ensemble": "Ensemble",
}


def _apply_dark(ax) -> None:
    ax.set_facecolor(_DARK_BG)
    ax.spines[:].set_color(_GRID)
    ax.tick_params(colors=_TEXT, labelsize=9)
    ax.title.set_color(_TEXT)
    ax.xaxis.label.set_color(_TEXT)
    ax.yaxis.label.set_color(_TEXT)
    ax.grid(color=_GRID, linewidth=0.6, alpha=0.6)


def _fetch_hit_trend(limit: int = 80) -> Dict[str, List[dict]]:
    """
    取最近若干期的累计命中率曲线
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT issue, model,
                   COUNT(*) AS tickets,
                   SUM(CASE WHEN prize_amount > 0 THEN 1 ELSE 0 END) AS wins
            FROM results
            GROUP BY issue, model
            ORDER BY issue ASC
            """
        ).fetchall()
    trend: Dict[str, List[dict]] = defaultdict(list)
    cum: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tickets": 0, "wins": 0})
    for r in rows:
        key = r["model"]
        cum[key]["tickets"] += r["tickets"] or 0
        cum[key]["wins"] += r["wins"] or 0
        rate = cum[key]["wins"] / cum[key]["tickets"] if cum[key]["tickets"] else 0
        trend[key].append({"issue": r["issue"], "rate": rate})
    # 只保留最近 limit 期
    for k in trend:
        trend[k] = trend[k][-limit:]
    return trend


def render_hit_trend(path: Optional[Path] = None) -> Optional[Path]:
    """
    渲染各模型累计命中率曲线

    @returns 图片路径；若无数据返回 None
    """
    data = _fetch_hit_trend()
    if not data:
        return None
    path = path or (IMG_DIR / "hit_trend.png")

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    fig.patch.set_facecolor(_DARK_BG)
    _apply_dark(ax)

    for model in MODELS:
        pts = data.get(model)
        if not pts:
            continue
        xs = [p["issue"] for p in pts]
        ys = [p["rate"] * 100 for p in pts]
        ax.plot(
            xs, ys, label=_EN_LABELS.get(model, model),
            color=_MODEL_COLORS.get(model, "#888"),
            linewidth=1.8, alpha=0.9,
        )

    ax.set_title("Cumulative Hit Rate (%)", fontsize=13, pad=10, weight="bold")
    ax.set_xlabel("Issue")
    ax.set_ylabel("Hit Rate (%)")
    ax.legend(
        loc="upper center", ncol=5, fontsize=8,
        bbox_to_anchor=(0.5, -0.15), frameon=False, labelcolor=_TEXT,
    )
    # x 轴稀疏显示
    all_issues = sorted({p["issue"] for pts in data.values() for p in pts})
    step = max(1, len(all_issues) // 8)
    ax.set_xticks(all_issues[::step])
    ax.tick_params(axis="x", rotation=30)

    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def render_latest_draw(issue: str, path: Optional[Path] = None) -> Optional[Path]:
    """
    渲染最近一期开奖号码球图（大大的）

    @param issue 期号
    @returns 图片路径
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT draw_date, front, back FROM draws WHERE issue = ?", (issue,)
        ).fetchone()
    if not row:
        return None

    front = decode(row["front"])
    back = decode(row["back"])

    path = path or (IMG_DIR / f"draw_{issue}.png")
    n = len(front) + len(back)
    fig, ax = plt.subplots(figsize=(max(n * 0.95, 7.5), 2.4), dpi=160)
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_BG)
    ax.set_xlim(-0.8, n - 0.2)
    ax.set_ylim(-1.4, 1.6)
    ax.axis("off")

    ax.text((n - 1) / 2, 1.25, f"Issue  {issue}",
            ha="center", va="center", color=_TEXT,
            fontsize=13, weight="bold")
    if row["draw_date"]:
        ax.text((n - 1) / 2, 0.85, f"Draw  {row['draw_date']}",
                ha="center", va="center", color=_MUTED, fontsize=9)

    for i, num in enumerate(front):
        circle = plt.Circle((i, 0), 0.42, color="#ef4444", ec="#b91c1c", lw=1)
        ax.add_patch(circle)
        ax.text(i, 0, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=15, weight="bold")

    sep_x = len(front) - 0.5
    ax.plot([sep_x + 0.1, sep_x + 0.1], [-0.3, 0.3], color="#6b7280", lw=2)

    for j, num in enumerate(back):
        idx = len(front) + j
        circle = plt.Circle((idx, 0), 0.42, color="#3b82f6", ec="#1d4ed8", lw=1)
        ax.add_patch(circle)
        ax.text(idx, 0, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=15, weight="bold")

    ax.text((n - 1) / 2, -0.95, "Front × 5   +   Back × 2",
            ha="center", va="center", color=_MUTED, fontsize=8)

    ax.set_aspect("equal")
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return path


def _draw_ticket(ax, cx: float, cy: float, front, back,
                 ball_r: float = 0.36, gap: float = 0.82,
                 hit_front: Optional[set] = None,
                 hit_back: Optional[set] = None) -> None:
    """
    在 ax 上（cx, cy）位置画一注号码：5 红 + 分隔 + 2 蓝

    @param hit_front 若传入，命中的前区号会加金色高亮外圈
    @param hit_back 若传入，命中的后区号会加金色高亮外圈
    """
    sep_w = 0.5
    for k, num in enumerate(front):
        x = cx + (k + 0.5) * gap
        hit = hit_front and num in hit_front
        ring = "#facc15" if hit else "#b91c1c"
        lw = 1.8 if hit else 0.6
        ax.add_patch(plt.Circle((x, cy), ball_r, color="#ef4444",
                                ec=ring, lw=lw, zorder=2))
        ax.text(x, cy, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=8.5, weight="bold", zorder=3)

    sep_x = cx + 5 * gap + sep_w * 0.3
    ax.plot([sep_x, sep_x], [cy - 0.28, cy + 0.28],
            color="#4b5563", lw=1, zorder=1)

    for k, num in enumerate(back):
        x = cx + 5 * gap + sep_w + (k + 0.5) * gap
        hit = hit_back and num in hit_back
        ring = "#facc15" if hit else "#1d4ed8"
        lw = 1.8 if hit else 0.6
        ax.add_patch(plt.Circle((x, cy), ball_r, color="#3b82f6",
                                ec=ring, lw=lw, zorder=2))
        ax.text(x, cy, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=8.5, weight="bold", zorder=3)


def _fetch_predictions(issue: str) -> Dict[str, List[dict]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT model, ticket_idx, front, back FROM predictions "
            "WHERE issue = ? ORDER BY model, ticket_idx",
            (issue,),
        ).fetchall()
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        buckets[r["model"]].append({
            "ticket_idx": r["ticket_idx"],
            "front": decode(r["front"]),
            "back": decode(r["back"]),
        })
    return buckets


def render_predictions_summary(issue: str,
                               path: Optional[Path] = None) -> Optional[Path]:
    """
    渲染本期全部模型预测汇总图（9 模型 × 4 注网格）

    @param issue 预测期号
    @returns 图片路径；若无预测返回 None
    """
    buckets = _fetch_predictions(issue)
    if not buckets:
        return None

    models = [m for m in MODELS if m in buckets]
    n_rows = len(models)

    label_w = 5.5
    ticket_w = 6.2
    ticket_gap = 0.9
    total_w = label_w + 4 * ticket_w + 3 * ticket_gap
    row_h = 1.0

    fig_w = 11.5
    fig_h = 0.9 + n_rows * 0.55 + 0.4
    path = path or (IMG_DIR / f"predictions_{issue}.png")

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_BG)
    ax.set_xlim(-0.3, total_w + 0.3)
    ax.set_ylim(-0.9, n_rows * row_h + 0.2)
    ax.invert_yaxis()
    ax.axis("off")

    ax.text(total_w / 2, -0.55, f"DaLeTou Predictions  ·  Issue {issue}",
            ha="center", va="center", color=_TEXT,
            fontsize=15, weight="bold")
    ax.text(total_w / 2, -0.15,
            f"{n_rows} Models  ×  4 Tickets   =   {n_rows * 4} combinations",
            ha="center", va="center", color=_MUTED, fontsize=9)

    for i, model in enumerate(models):
        y = i * row_h + 0.6
        color = _MODEL_COLORS.get(model, "#888")
        ax.add_patch(plt.Rectangle(
            (-0.15, y - 0.4), total_w + 0.3, 0.85,
            color=_CARD_BG if i % 2 == 0 else _DARK_BG,
            zorder=0,
        ))
        ax.add_patch(plt.Rectangle(
            (-0.15, y - 0.4), 0.18, 0.85,
            color=color, zorder=1,
        ))
        ax.text(0.3, y, _EN_LABELS.get(model, model),
                color=color, fontsize=11, weight="bold",
                va="center", ha="left", zorder=2)

        tickets = sorted(buckets[model], key=lambda t: t["ticket_idx"])[:4]
        for j, t in enumerate(tickets):
            x0 = label_w + j * (ticket_w + ticket_gap)
            _draw_ticket(ax, x0, y, t["front"], t["back"])

    ax.set_aspect("equal")
    fig.savefig(path, facecolor=fig.get_facecolor(),
                bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return path


def render_evaluate_summary(issue: str,
                            path: Optional[Path] = None) -> Optional[Path]:
    """
    渲染开奖命中汇总图：顶部开奖球，下方每模型 4 注并高亮命中号码

    @param issue 刚开奖的期号
    """
    with get_conn() as conn:
        draw = conn.execute(
            "SELECT draw_date, front, back FROM draws WHERE issue = ?", (issue,)
        ).fetchone()
    if not draw:
        return None

    buckets = _fetch_predictions(issue)
    if not buckets:
        return None

    front_set = set(decode(draw["front"]))
    back_set = set(decode(draw["back"]))
    draw_front = decode(draw["front"])
    draw_back = decode(draw["back"])

    models = [m for m in MODELS if m in buckets]
    n_rows = len(models)

    label_w = 5.5
    ticket_w = 6.2
    ticket_gap = 0.9
    total_w = label_w + 4 * ticket_w + 3 * ticket_gap
    row_h = 1.0
    head_h = 3.2

    fig_w = 11.5
    fig_h = head_h * 0.45 + 0.5 + n_rows * 0.55 + 0.4
    path = path or (IMG_DIR / f"evaluate_{issue}.png")

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_BG)
    ax.set_xlim(-0.3, total_w + 0.3)
    ax.set_ylim(-head_h, n_rows * row_h + 0.2)
    ax.invert_yaxis()
    ax.axis("off")

    ax.text(total_w / 2, -head_h + 0.3,
            f"Issue {issue}  ·  Result", ha="center", va="center",
            color=_TEXT, fontsize=15, weight="bold")
    if draw["draw_date"]:
        ax.text(total_w / 2, -head_h + 0.8,
                f"Draw  {draw['draw_date']}", ha="center", va="center",
                color=_MUTED, fontsize=9)

    head_cx = (total_w - (7 * 0.95)) / 2
    for k, num in enumerate(draw_front):
        x = head_cx + (k + 0.5) * 0.95
        ax.add_patch(plt.Circle((x, -head_h + 1.8), 0.44,
                                color="#ef4444", ec="#facc15", lw=1.2, zorder=2))
        ax.text(x, -head_h + 1.8, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=13, weight="bold", zorder=3)
    sep_x = head_cx + 5 * 0.95 + 0.2
    ax.plot([sep_x, sep_x], [-head_h + 1.4, -head_h + 2.2],
            color="#6b7280", lw=2)
    for k, num in enumerate(draw_back):
        x = head_cx + 5 * 0.95 + 0.4 + (k + 0.5) * 0.95
        ax.add_patch(plt.Circle((x, -head_h + 1.8), 0.44,
                                color="#3b82f6", ec="#facc15", lw=1.2, zorder=2))
        ax.text(x, -head_h + 1.8, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=13, weight="bold", zorder=3)

    ax.text(total_w / 2, -0.25,
            "Predictions  ·  Hit numbers highlighted in gold",
            ha="center", va="center", color=_MUTED, fontsize=9)

    for i, model in enumerate(models):
        y = i * row_h + 0.6
        color = _MODEL_COLORS.get(model, "#888")
        ax.add_patch(plt.Rectangle(
            (-0.15, y - 0.4), total_w + 0.3, 0.85,
            color=_CARD_BG if i % 2 == 0 else _DARK_BG, zorder=0,
        ))
        ax.add_patch(plt.Rectangle(
            (-0.15, y - 0.4), 0.18, 0.85, color=color, zorder=1,
        ))

        tickets = sorted(buckets[model], key=lambda t: t["ticket_idx"])[:4]
        hit_cnt = 0
        for t in tickets:
            if set(t["front"]) & front_set or set(t["back"]) & back_set:
                hit_cnt += 1

        ax.text(0.3, y, _EN_LABELS.get(model, model),
                color=color, fontsize=10.5, weight="bold",
                va="center", ha="left", zorder=2)
        ax.text(0.3, y + 0.28, f"{hit_cnt}/4 tickets hit",
                color=_MUTED, fontsize=7.5,
                va="center", ha="left", zorder=2)

        for j, t in enumerate(tickets):
            x0 = label_w + j * (ticket_w + ticket_gap)
            _draw_ticket(ax, x0, y, t["front"], t["back"],
                         hit_front=front_set, hit_back=back_set)

    ax.set_aspect("equal")
    fig.savefig(path, facecolor=fig.get_facecolor(),
                bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return path


def run(predict_issue: Optional[str] = None,
        evaluate_issue: Optional[str] = None) -> None:
    """
    生成全部图表（供定时任务调用）

    @param predict_issue 待预测期号（为其生成 predictions_summary）
    @param evaluate_issue 已开奖期号（为其生成 draw + evaluate_summary）
    """
    p1 = render_hit_trend()
    print(f"hit_trend 图：{p1}")

    with get_conn() as conn:
        latest = conn.execute(
            "SELECT issue FROM draws ORDER BY issue DESC LIMIT 1"
        ).fetchone()
    if latest:
        issue = latest["issue"]
        print(f"最新开奖图：{render_latest_draw(issue)}")
        if evaluate_issue is None:
            evaluate_issue = issue

    if evaluate_issue:
        print(f"开奖命中汇总图：{render_evaluate_summary(evaluate_issue)}")

    if predict_issue:
        print(f"预测汇总图：{render_predictions_summary(predict_issue)}")
    else:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT issue FROM predictions ORDER BY issue DESC LIMIT 1"
            ).fetchone()
        if row:
            print(f"预测汇总图：{render_predictions_summary(row['issue'])}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--predict-issue", default=None)
    parser.add_argument("--evaluate-issue", default=None)
    args = parser.parse_args()
    run(predict_issue=args.predict_issue, evaluate_issue=args.evaluate_issue)
