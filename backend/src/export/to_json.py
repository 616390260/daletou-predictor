"""
把数据库里的内容导出为前端可直接读取的 JSON 文件
导出目录：data/export/
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Dict

from ..config import (
    BACK_MAX,
    BACK_MIN,
    EXPORT_DIR,
    FRONT_MAX,
    FRONT_MIN,
    MODEL_LABELS,
    MODELS,
    TICKET_PRICE,
    TICKETS_PER_DRAW,
)
from ..db import get_conn, init_db
from ..utils.numbers import decode


def _write_json(name: str, data: Any) -> None:
    """
    写入 JSON，紧凑模式，utf-8
    """
    path = EXPORT_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"已导出 {path}  ({path.stat().st_size / 1024:.1f} KB)")


def export_history(limit: int = 10000) -> None:
    """
    导出历史开奖记录

    @param limit 导出最新 N 期（默认 10000，即全量；当前历史约 2800+ 期约 230KB，浏览器可接受）
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT issue, draw_date, front, back, sales, pool
            FROM draws ORDER BY issue DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    items = [
        {
            "issue": r["issue"],
            "date": r["draw_date"],
            "front": decode(r["front"]),
            "back": decode(r["back"]),
            "sales": r["sales"],
            "pool": r["pool"],
        }
        for r in rows
    ]
    _write_json("history.json", items)


def export_frequency() -> None:
    """
    导出历史号码出现频次（近 100 期、近 500 期、全部）
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT front, back FROM draws ORDER BY issue DESC"
        ).fetchall()

    def _count(records: list, lo: int, hi: int, key: str) -> Dict[str, int]:
        c: Counter[int] = Counter()
        for r in records:
            for n in decode(r[key]):
                c[n] += 1
        return {str(n): c.get(n, 0) for n in range(lo, hi + 1)}

    windows = {"recent100": rows[:100], "recent500": rows[:500], "all": list(rows)}
    result = {
        name: {
            "front": _count(recs, FRONT_MIN, FRONT_MAX, "front"),
            "back": _count(recs, BACK_MIN, BACK_MAX, "back"),
            "count": len(recs),
        }
        for name, recs in windows.items()
    }
    _write_json("frequency.json", result)


def export_predictions(limit_issues: int = 50) -> None:
    """
    导出最近若干期的预测记录（每期每模型 TICKETS_PER_DRAW 注 + 命中情况）
    """
    with get_conn() as conn:
        issue_rows = conn.execute(
            "SELECT DISTINCT issue FROM predictions ORDER BY issue DESC LIMIT ?",
            (limit_issues,),
        ).fetchall()
        issues = [r["issue"] for r in issue_rows]
        if not issues:
            _write_json("predictions.json", [])
            return

        placeholder = ",".join("?" * len(issues))
        preds = conn.execute(
            f"""
            SELECT issue, model, ticket_idx, front, back
            FROM predictions WHERE issue IN ({placeholder})
            ORDER BY issue DESC, model, ticket_idx
            """,
            issues,
        ).fetchall()
        res = conn.execute(
            f"""
            SELECT issue, model, ticket_idx, front_hit, back_hit, prize_level, prize_amount
            FROM results WHERE issue IN ({placeholder})
            """,
            issues,
        ).fetchall()
        draws = conn.execute(
            f"""
            SELECT issue, draw_date, front, back
            FROM draws WHERE issue IN ({placeholder})
            """,
            issues,
        ).fetchall()

    draw_map = {
        d["issue"]: {"date": d["draw_date"], "front": decode(d["front"]), "back": decode(d["back"])}
        for d in draws
    }
    result_map = {
        (r["issue"], r["model"], r["ticket_idx"]): {
            "front_hit": r["front_hit"],
            "back_hit": r["back_hit"],
            "level": r["prize_level"],
            "amount": r["prize_amount"],
        }
        for r in res
    }

    grouped: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"models": defaultdict(list)})
    for p in preds:
        issue = p["issue"]
        entry = grouped[issue]
        entry.setdefault("issue", issue)
        entry.setdefault("real", draw_map.get(issue))
        entry["models"][p["model"]].append(
            {
                "idx": p["ticket_idx"],
                "front": decode(p["front"]),
                "back": decode(p["back"]),
                "result": result_map.get((issue, p["model"], p["ticket_idx"])),
            }
        )

    items = []
    for issue in issues:
        entry = grouped.get(issue)
        if entry is None:
            continue
        models_out = []
        for m, tickets in entry["models"].items():
            tickets.sort(key=lambda t: t["idx"])
            models_out.append({"model": m, "label": MODEL_LABELS.get(m, m), "tickets": tickets})
        models_out.sort(key=lambda x: MODELS.index(x["model"]) if x["model"] in MODELS else 99)
        items.append({"issue": issue, "real": entry.get("real"), "models": models_out})

    _write_json("predictions.json", items)


def export_stats() -> None:
    """
    导出各模型的长期命中率统计
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT model,
                   COUNT(*)                                        AS total_tickets,
                   COUNT(DISTINCT issue)                           AS total_issues,
                   SUM(CASE WHEN prize_amount > 0 THEN 1 ELSE 0 END) AS win_tickets,
                   SUM(prize_amount)                               AS total_prize,
                   SUM(CASE WHEN front_hit >= 1 THEN 1 ELSE 0 END) AS any_front_hit,
                   AVG(front_hit * 1.0)                            AS avg_front_hit,
                   AVG(back_hit * 1.0)                             AS avg_back_hit
            FROM results
            GROUP BY model
            """
        ).fetchall()

    stats = []
    for r in rows:
        tickets = r["total_tickets"] or 0
        issues = r["total_issues"] or 0
        cost = tickets * TICKET_PRICE
        prize = r["total_prize"] or 0
        stats.append(
            {
                "model": r["model"],
                "label": MODEL_LABELS.get(r["model"], r["model"]),
                "issues": issues,
                "tickets": tickets,
                "win_tickets": r["win_tickets"] or 0,
                "hit_rate": (r["win_tickets"] or 0) / tickets if tickets else 0,
                "avg_front_hit": r["avg_front_hit"] or 0,
                "avg_back_hit": r["avg_back_hit"] or 0,
                "cost": cost,
                "total_prize": prize,
                "roi": (prize - cost) / cost if cost else 0,
            }
        )
    stats.sort(
        key=lambda s: MODELS.index(s["model"]) if s["model"] in MODELS else 99
    )

    with get_conn() as conn:
        ts_rows = conn.execute(
            """
            SELECT issue, model,
                   SUM(prize_amount) AS prize,
                   COUNT(*)          AS tickets
            FROM results
            GROUP BY issue, model
            ORDER BY issue ASC
            """
        ).fetchall()

    trend: Dict[str, list] = defaultdict(list)
    cumulative: Dict[str, Dict[str, float]] = defaultdict(lambda: {"prize": 0.0, "cost": 0.0})
    for r in ts_rows:
        key = r["model"]
        cumulative[key]["prize"] += r["prize"] or 0
        cumulative[key]["cost"] += (r["tickets"] or 0) * TICKET_PRICE
        roi = (cumulative[key]["prize"] - cumulative[key]["cost"]) / cumulative[key]["cost"] if cumulative[key]["cost"] else 0
        trend[key].append({"issue": r["issue"], "roi": roi})

    # 滚动命中率曲线：每一期的"累计中奖注数/累计总注数"
    with get_conn() as conn:
        hit_rows = conn.execute(
            """
            SELECT issue, model,
                   COUNT(*) AS tickets,
                   SUM(CASE WHEN prize_amount > 0 THEN 1 ELSE 0 END) AS wins
            FROM results
            GROUP BY issue, model
            ORDER BY issue ASC
            """
        ).fetchall()
    hit_trend: Dict[str, list] = defaultdict(list)
    cum_hit: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tickets": 0, "wins": 0})
    for r in hit_rows:
        key = r["model"]
        cum_hit[key]["tickets"] += r["tickets"] or 0
        cum_hit[key]["wins"] += r["wins"] or 0
        rate = cum_hit[key]["wins"] / cum_hit[key]["tickets"] if cum_hit[key]["tickets"] else 0
        hit_trend[key].append({"issue": r["issue"], "rate": rate})

    _write_json("stats.json", {"summary": stats, "trend": trend, "hit_trend": hit_trend})


def _next_draw_time(latest_date_str: str | None) -> str | None:
    """
    估算下一次大乐透开奖时间（北京时间周一/三/六 20:30）

    @param latest_date_str 最新一期开奖日期 YYYY-MM-DD
    @returns ISO 字符串（UTC+8 时区）
    """
    from datetime import datetime, timedelta, timezone

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    if latest_date_str:
        try:
            base = datetime.strptime(latest_date_str, "%Y-%m-%d").replace(
                hour=20, minute=30, tzinfo=tz
            )
            now = max(now, base + timedelta(minutes=1))
        except Exception:
            pass
    # 大乐透：周一=0 / 周三=2 / 周六=5
    draw_weekdays = {0, 2, 5}
    for offset in range(0, 8):
        candidate = now + timedelta(days=offset)
        candidate = candidate.replace(hour=20, minute=30, second=0, microsecond=0)
        if candidate < now:
            continue
        if candidate.weekday() in draw_weekdays:
            return candidate.isoformat()
    return None


def export_meta() -> None:
    """
    导出元信息（最后更新时间、总数等），给前端展示数据新鲜度
    """
    from datetime import datetime

    with get_conn() as conn:
        draws = conn.execute("SELECT COUNT(*) c FROM draws").fetchone()["c"]
        latest = conn.execute(
            "SELECT issue, draw_date FROM draws ORDER BY issue DESC LIMIT 1"
        ).fetchone()
        preds = conn.execute("SELECT COUNT(*) c FROM predictions").fetchone()["c"]
        results = conn.execute("SELECT COUNT(*) c FROM results").fetchone()["c"]
        next_pred = conn.execute(
            "SELECT issue FROM predictions ORDER BY issue DESC LIMIT 1"
        ).fetchone()

    latest_issue = latest["issue"] if latest else None
    latest_date = latest["draw_date"] if latest else None
    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_draws": draws,
        "latest_issue": latest_issue,
        "latest_date": latest_date,
        "next_draw_at": _next_draw_time(latest_date),
        "predicting_issue": next_pred["issue"] if next_pred else None,
        "total_predictions": preds,
        "total_results": results,
        "tickets_per_draw": TICKETS_PER_DRAW,
        "ticket_price": TICKET_PRICE,
        "models": [{"key": k, "label": v} for k, v in MODEL_LABELS.items()],
    }
    _write_json("meta.json", meta)


def run() -> None:
    """
    导出全部 JSON
    """
    init_db()
    export_meta()
    export_history()
    export_frequency()
    export_predictions()
    export_stats()
    print("全部 JSON 导出完成")


if __name__ == "__main__":
    run()
