"""Evaluate verified single-ticket predictions with finite-population draw statistics."""
from __future__ import annotations

import json
import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from ..config import BACK_COUNT, BACK_MAX, EXPORT_DIR, FRONT_COUNT, FRONT_MAX, MODELS, PRIZE_TABLE
from ..db import get_conn

THEORETICAL_FRONT = FRONT_COUNT / FRONT_MAX
THEORETICAL_BACK = BACK_COUNT / BACK_MAX
LOG_ROOT = Path(__file__).resolve().parents[3] / "docs"


@lru_cache(maxsize=128)
def hit_distribution(periods: int, population: int, picks: int) -> tuple[float, ...]:
    """Convolve whole-draw hypergeometric hit counts across independent issues.

    @returns P(total hits=k), retaining dependence among slots of one ticket.
    """
    if periods < 0 or not 0 < picks <= population:
        raise ValueError("Invalid draw distribution parameters")
    denominator = math.comb(population, picks)
    one = [math.comb(picks, h) * math.comb(population - picks, picks - h) / denominator
           if 0 <= picks - h <= population - picks else 0.0 for h in range(picks + 1)]
    result = [1.0]
    for _ in range(periods):
        next_result = [0.0] * (len(result) + picks)
        for i, probability in enumerate(result):
            for j, weight in enumerate(one):
                next_result[i + j] += probability * weight
        result = next_result
    total = sum(result)
    return tuple(p / total for p in result)


def _mass_test(k: int, pmf: tuple[float, ...]) -> float:
    """@returns Two-sided probability-ordering exact p value."""
    if not 0 <= k < len(pmf):
        raise ValueError("Observed hits outside the possible range")
    return min(1.0, sum(p for p in pmf if p <= pmf[k] * (1 + 1e-12)))


def exact_hit_test(hits: int, periods: int, population: int, picks: int) -> float:
    """@returns Exact test of total hits under uniform independent draws."""
    return _mass_test(hits, hit_distribution(periods, population, picks))


def holm_adjust(values: list[float]) -> list[float]:
    """@returns Holm-adjusted p values, valid without independence between models."""
    adjusted = [1.0] * len(values)
    previous = 0.0
    for rank, index in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        previous = max(previous, min(1.0, (len(values) - rank) * values[index]))
        adjusted[index] = previous
    return adjusted


def _null_interval(pmf: tuple[float, ...], slots: int) -> list[float]:
    """@returns Equal-tail 95% null reference range, not an observed-rate CI."""
    bounds = []
    for quantile in (0.025, 0.975):
        cumulative = 0.0
        for k, probability in enumerate(pmf):
            cumulative += probability
            if cumulative >= quantile:
                bounds.append(k / slots)
                break
    return bounds


def _eligible(issue: str, draw_date: str, created: str, ranges: list, logged: dict) -> bool:
    """Accept audited simulations or logged predictions made before the draw."""
    if any(start <= issue <= end for start, end in ranges):
        return True
    if issue not in logged:
        return False
    try:
        draw_at = datetime.fromisoformat(draw_date + "T20:30:00+08:00")
        created_at = datetime.fromisoformat(created)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at < draw_at and any(ts < draw_at for ts in logged[issue])
    except (TypeError, ValueError):
        return False


def _collect_per_model_hits(log_paths: list[Path] | None = None) -> dict:
    """Collect only ticket zero with audited provenance or a pre-draw prediction log."""
    ranges, logged = [], defaultdict(list)
    for path in log_paths if log_paths is not None else sorted(LOG_ROOT.glob("RUN_LOG*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("outcome") != "success":
                continue
            extra = record.get("extra") or {}
            if extra.get("recovery") is True and extra.get("historical_simulation") is True:
                start, end = extra.get("start_issue", ""), extra.get("end_issue", "")
                if re.fullmatch(r"\d{5}", start) and re.fullmatch(r"\d{5}", end) and start <= end:
                    ranges.append((start, end))
            issue = extra.get("predicted_issue")
            if record.get("workflow") == "predict" and isinstance(issue, str) and re.fullmatch(r"\d{5}", issue):
                try:
                    ts = datetime.fromisoformat(record.get("ts") or "")
                    if ts.tzinfo is not None:
                        logged[issue].append(ts)
                except ValueError:
                    continue
    stat = defaultdict(lambda: {"front_hits": 0, "front_slots": 0, "back_hits": 0,
                                "back_slots": 0, "issues": set(), "tickets": 0, "wins": 0})
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT r.issue,r.model,r.front_hit,r.back_hit,r.prize_amount,d.draw_date,p.created_at
            FROM results r JOIN draws d ON d.issue=r.issue
            JOIN predictions p ON p.issue=r.issue AND p.model=r.model AND p.ticket_idx=r.ticket_idx
            WHERE r.ticket_idx=0 ORDER BY r.issue
        """).fetchall()
    for row in rows:
        if row["model"] not in MODELS or not _eligible(row["issue"], row["draw_date"], row["created_at"], ranges, logged):
            continue
        s = stat[row["model"]]
        s["front_hits"] += row["front_hit"]
        s["back_hits"] += row["back_hit"]
        s["front_slots"] += FRONT_COUNT
        s["back_slots"] += BACK_COUNT
        s["issues"].add(row["issue"])
        s["tickets"] += 1
        s["wins"] += row["prize_amount"] > 0
    return dict(stat)


def _win_probability() -> float:
    """@returns Any-prize probability under the project's 5+2 prize conditions."""
    front, back = hit_distribution(1, FRONT_MAX, FRONT_COUNT), hit_distribution(1, BACK_MAX, BACK_COUNT)
    return sum(front[f] * back[b] for f, b in PRIZE_TABLE)


def _win_test(wins: int, periods: int, probability: float) -> float:
    # One prize event per issue is Bernoulli; number slots within that issue are not.
    pmf = tuple(math.exp(math.lgamma(periods + 1) - math.lgamma(k + 1) - math.lgamma(periods - k + 1)
                          + k * math.log(probability) + (periods - k) * math.log1p(-probability))
                for k in range(periods + 1))
    return _mass_test(wins, pmf)


def compute_significance() -> list[dict]:
    """Return audited per-model hit tests and corrected winning-event tests."""
    out, probabilities = [], []
    prior = _win_probability()
    for model, s in sorted(_collect_per_model_hits().items()):
        n = s["tickets"]
        regions = {}
        for key, population, picks in (("front", FRONT_MAX, FRONT_COUNT), ("back", BACK_MAX, BACK_COUNT)):
            pmf = hit_distribution(n, population, picks)
            interval = _null_interval(pmf, n * picks)
            regions[key] = {
                "hits": s[f"{key}_hits"], "slots": n * picks,
                "observed": s[f"{key}_hits"] / (n * picks), "theoretical": picks / population,
                "null_interval95": interval,
                "ci95": interval,  # Legacy key retained for cached clients; it is a null range.
                "p_value": _mass_test(s[f"{key}_hits"], pmf),
            }
        regions["win"] = {"hits": s["wins"], "slots": n, "observed": s["wins"] / n,
                          "theoretical": prior, "p_value": _win_test(s["wins"], n, prior)}
        item = {"model": model, "issues": n, "tickets": n, "win_tickets": s["wins"],
                "win_rate": s["wins"] / n, "first_issue": min(s["issues"]), "last_issue": max(s["issues"]),
                "issue_set_sha256": hashlib.sha256(json.dumps(sorted(s["issues"])).encode()).hexdigest(), **regions}
        out.append(item)
        probabilities.extend(item[key]["p_value"] for key in ("front", "back", "win"))
    adjusted = iter(holm_adjust(probabilities))
    for item in out:
        parts = []
        for key, label in (("front", "前区"), ("back", "后区"), ("win", "中奖率")):
            region = item[key]
            region["adjusted_p_value"] = next(adjusted)
            region["significant"] = region["adjusted_p_value"] < 0.05 and item["issues"] >= 30
            if region["significant"]:
                direction = "高于" if region["observed"] > region["theoretical"] else "低于"
                parts.append(f"{label}{direction}理论随机基线（校正 p={region['adjusted_p_value']:.3g}）")
        item["verdict"] = ("样本少于 30 期，仅供观察" if item["issues"] < 30 else
                           "；".join(parts) + "，仍需后续前瞻验证" if parts else
                           "多重校正后，未检测到与理论随机基线的显著差异")
    return out


def export_significance() -> None:
    """Export truthful statistical scope without asserting unverified backtests are clean."""
    data = {
        "methodology": {
            "name": "Verified per-issue hypergeometric tests + Holm correction",
            "description": "仅纳入已核验的逐期补算或有开奖前运行日志的真实预测，每模型每期第 1 注。前后区按不放回抽样的超几何分布逐期卷积；中奖事件按期做二项检验。对全部模型、前后区及中奖率使用 Holm 多重校正。图中区间为理论随机基线的 95% 参考范围，并非观测率置信区间。",
            "theoretical_front": THEORETICAL_FRONT, "theoretical_back": THEORETICAL_BACK,
            "theoretical_win": _win_probability(), "significance_level": 0.05,
            "scope": "verified_only", "excluded": "未核验的旧补算和同一期额外注数不进入显著性判断；全库汇总仅是历史描述。",
            "analysis_type": "exploratory",
            "sources": ["https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.hypergeom.html"],
        },
        "models": compute_significance(),
    }
    path = EXPORT_DIR / "significance.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"已导出 {path}")


if __name__ == "__main__":
    export_significance()
