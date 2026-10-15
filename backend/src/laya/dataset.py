"""Build independently verified, chronological Laya training examples."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from ..config import MODELS, PRIZE_TABLE
from ..utils.numbers import count_hits, decode
from ..utils.prizes import previous_pool, prize_for_hits

FEATURE_VERSION = "daletou-pre-draw-v1"
TASK = {
    "name": "daletou-decision",
    "description": "仅使用开奖前信息评审原九模型候选；输出为模型评分。",
    "question": {
        "type": "choice",
        "instructions": "仅基于开奖前的候选与历史状态，评估候选在目标期的中奖倾向。",
        "criteria": {"A": "目标期该注中奖", "B": "目标期该注未中奖"},
    },
}


def _issue(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{5}", value):
        raise ValueError(f"Invalid issue: {value!r}")
    return value


def _ticket(front: list[int], back: list[int]) -> tuple[list[int], list[int]]:
    for numbers, count, maximum in ((front, 5, 35), (back, 2, 12)):
        if (len(numbers) != count or any(type(n) is not int for n in numbers)
                or len(set(numbers)) != count
                or any(n < 1 or n > maximum for n in numbers)):
            raise ValueError("Candidate requires unique integer numbers: exactly 5+2 within range")
    return sorted(front), sorted(back)


def build_state(
    conn: sqlite3.Connection, issue: str, model: str,
    front: list[int], back: list[int], verified_start: str,
) -> str:
    """Describe a candidate using only data available before its target issue.

    @param verified_start First issue with trusted historical model outcomes.
    @returns Compact JSON text with no target or future outcome features.
    """
    _issue(issue)
    _issue(verified_start)
    if model not in MODELS:
        raise ValueError(f"Unknown candidate model: {model}")
    front, back = _ticket(front, back)
    draws = conn.execute(
        "SELECT front,back FROM draws WHERE issue < ? ORDER BY issue DESC LIMIT 30",
        (issue,),
    ).fetchall()
    fronts = [decode(row[0]) for row in draws]
    backs = [decode(row[1]) for row in draws]
    results = conn.execute(
        """SELECT front_hit,back_hit,prize_amount FROM results
           WHERE model=? AND ticket_idx=0 AND issue>=? AND issue<?
           ORDER BY issue DESC LIMIT 30""",
        (model, verified_start, issue),
    ).fetchall()
    count = len(results)
    state = {
        "version": FEATURE_VERSION,
        "issue": issue,
        "model": model,
        "front": front,
        "back": back,
        "front_sum": sum(front),
        "front_odd": sum(n % 2 for n in front),
        "draws_n": len(draws),
        "front_freq30": [sum(n in row for row in fronts) for n in front],
        "back_freq30": [sum(n in row for row in backs) for n in back],
        "model_history_n": count,
        "model_front_hit30": round(sum(row[0] for row in results) / count, 6) if count else 0.0,
        "model_back_hit30": round(sum(row[1] for row in results) / count, 6) if count else 0.0,
        "model_win_rate30": round(sum(row[2] > 0 for row in results) / count, 6) if count else 0.0,
    }
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def _verified_ranges(log_path: Path) -> list[tuple[str, str]]:
    ranges = []
    for number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid provenance log line {number}") from exc
        extra = record.get("extra") or {}
        if (record.get("outcome") == "success" and extra.get("recovery") is True
                and extra.get("historical_simulation") is True):
            start, end = _issue(extra.get("start_issue")), _issue(extra.get("end_issue"))
            if start > end:
                raise ValueError(f"Invalid verified range: {start}..{end}")
            ranges.append((start, end))
    if not ranges:
        raise ValueError("No verified historical simulation provenance found")
    merged = []
    for start, end in sorted(ranges):
        if merged and int(start) <= int(merged[-1][1]) + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)


def build_dataset(conn: sqlite3.Connection, log_path: Path, output_dir: Path) -> dict:
    """Verify recovery candidates and split complete issues chronologically.

    V1 result amounts remain legacy estimates for frozen dataset compatibility,
    not actual returns. Stored results may use either independently verified rule.

    @returns Metadata for the written all/train/validation/test JSONL files.
    """
    ranges = _verified_ranges(Path(log_path))
    draws = []
    for start, end in ranges:
        draws.extend(conn.execute(
            "SELECT issue,front,back FROM draws WHERE issue>=? AND issue<=? ORDER BY issue",
            (start, end),
        ).fetchall())
    if len(draws) < 6:
        raise ValueError("At least 6 verified issues are required for chronological splits")
    issues = [draw[0] for draw in draws]
    rows = []
    for issue, real_front, real_back in draws:
        real_front, real_back = _ticket(decode(real_front), decode(real_back))
        candidates = conn.execute(
            "SELECT model,front,back FROM predictions WHERE issue=? AND ticket_idx=0", (issue,),
        ).fetchall()
        outcomes = conn.execute(
            """SELECT model,front_hit,back_hit,prize_level,prize_amount
               FROM results WHERE issue=? AND ticket_idx=0""", (issue,),
        ).fetchall()
        candidate_map = {row[0]: row for row in candidates}
        outcome_map = {row[0]: row for row in outcomes}
        missing = [model for model in MODELS if model not in candidate_map or model not in outcome_map]
        if missing:
            raise ValueError(f"Issue {issue} is missing complete candidates/results: {','.join(missing)}")
        verified_start = next(start for start, end in ranges if start <= issue <= end)
        pool_before = previous_pool(conn, issue)
        for model in MODELS:
            candidate, outcome = candidate_map[model], outcome_map[model]
            try:
                front, back = _ticket(decode(candidate[1]), decode(candidate[2]))
            except ValueError as exc:
                raise ValueError(f"Issue {issue} model {model}: invalid candidate") from exc
            front_hit, back_hit = count_hits(front, back, real_front, real_back)
            level, amount = PRIZE_TABLE.get((front_hit, back_hit), (None, 0))
            current_level, current_amount = prize_for_hits(issue, front_hit, back_hit, pool_before)
            valid_outcomes = {
                (front_hit, back_hit, level, amount),
                (front_hit, back_hit, current_level, current_amount),
            }
            if tuple(outcome[1:]) not in valid_outcomes:
                raise ValueError(f"Issue {issue} model {model}: stored result differs from independent recomputation")
            won = amount > 0
            rows.append({
                "id": f"{issue}:{model}", "issue": issue, "model": model,
                "front": front, "back": back,
                "state": build_state(conn, issue, model, front, back, verified_start),
                "label": "A" if won else "B", "probs": {"A": float(won), "B": float(not won)},
                "result": {"front_hit": front_hit, "back_hit": back_hit, "level": level, "amount": amount},
            })
    train_count, validation_count = int(len(issues) * 0.7), max(1, int(len(issues) * 0.15))
    split_issues = {
        "train": issues[:train_count],
        "validation": issues[train_count:train_count + validation_count],
        "test": issues[train_count + validation_count:],
    }
    all_text = _jsonl(rows)
    meta = {
        "issues": len(issues), "tickets": len(rows),
        "verified_start_issue": issues[0], "verified_end_issue": issues[-1],
        "verified_ranges": [{"start_issue": start, "end_issue": end} for start, end in ranges],
        "split_issues": split_issues,
        "split_counts": {split: len(values) * len(MODELS) for split, values in split_issues.items()},
        "cutoffs": {split: {"first_issue": values[0], "last_issue": values[-1]}
                    for split, values in split_issues.items()},
        "feature_version": FEATURE_VERSION,
        "dataset_sha256": hashlib.sha256(all_text.encode("utf-8")).hexdigest(),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "all.jsonl").write_text(all_text, encoding="utf-8")
    for split, values in split_issues.items():
        included = set(values)
        (output_dir / f"{split}.jsonl").write_text(_jsonl([row for row in rows if row["issue"] in included]), encoding="utf-8")
    (output_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "task.json").write_text(json.dumps(TASK, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta
