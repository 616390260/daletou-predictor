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
_TEXT = "#e5e7eb"
_GRID = "#1f2937"


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
            xs, ys, label=MODEL_LABELS.get(model, model),
            color=_MODEL_COLORS.get(model, "#888"),
            linewidth=1.8, alpha=0.9,
        )

    ax.set_title("各模型累计命中率（%）", fontsize=13, pad=10, weight="bold")
    ax.set_xlabel("期号")
    ax.set_ylabel("累计命中率 (%)")
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

    from ..utils.numbers import decode
    front = decode(row["front"])
    back = decode(row["back"])

    path = path or (IMG_DIR / f"draw_{issue}.png")
    n = len(front) + len(back)
    fig, ax = plt.subplots(figsize=(n * 0.9, 1.6), dpi=160)
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_BG)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(-0.8, 0.8)
    ax.axis("off")

    for i, num in enumerate(front):
        circle = plt.Circle((i, 0), 0.38, color="#ef4444", ec="#b91c1c", lw=1)
        ax.add_patch(circle)
        ax.text(i, 0, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=14, weight="bold")

    sep_x = len(front) - 0.5
    ax.plot([sep_x + 0.1, sep_x + 0.1], [-0.25, 0.25], color="#6b7280", lw=2)

    for j, num in enumerate(back):
        idx = len(front) + j
        circle = plt.Circle((idx, 0), 0.38, color="#3b82f6", ec="#1d4ed8", lw=1)
        ax.add_patch(circle)
        ax.text(idx, 0, f"{num:02d}", ha="center", va="center",
                color="#fff", fontsize=14, weight="bold")

    ax.set_aspect("equal")
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return path


def run() -> None:
    """
    生成全部图表（供定时任务调用）
    """
    p1 = render_hit_trend()
    print(f"hit_trend 图：{p1}")

    with get_conn() as conn:
        latest = conn.execute(
            "SELECT issue FROM draws ORDER BY issue DESC LIMIT 1"
        ).fetchone()
    if latest:
        p2 = render_latest_draw(latest["issue"])
        print(f"最新开奖图：{p2}")


if __name__ == "__main__":
    run()
