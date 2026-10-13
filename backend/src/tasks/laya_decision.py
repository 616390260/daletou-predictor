"""CLI for local Laya training, frozen evaluation and independent candidate selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import DATA_DIR, EXPORT_DIR, MODEL_LABELS, MODELS, PRIZE_TABLE
from ..db import get_conn
from ..laya.dataset import build_dataset, build_state
from ..laya.experiment import evaluate_version, local_model_lock, resolve_checkpoint, train_version, write_report
from ..laya.runtime import LayaScorer, choose_candidate
from ..utils.numbers import count_hits, decode

DATASET = DATA_DIR / "laya"
REPORT = EXPORT_DIR / "laya.json"


def decide(issue: str, manifest: dict) -> dict:
    """Select one already existing ticket, without generating original model predictions."""
    meta = json.loads((DATASET / "metadata.json").read_text())
    with get_conn() as conn:
        candidates = conn.execute(
            "SELECT model,front,back FROM predictions WHERE issue=? AND ticket_idx=0", (issue,),
        ).fetchall()
        if {r["model"] for r in candidates} != set(MODELS) or len(candidates) != len(MODELS):
            raise ValueError(f"Issue {issue} requires all 9 original candidates first")
        states = []
        for row in candidates:
            front, back = decode(row["front"]), decode(row["back"])
            state = build_state(conn, issue, row["model"], front, back, meta["verified_start_issue"])
            states.append({"model": row["model"], "front": front, "back": back, "state": state})
        draw = conn.execute("SELECT front,back FROM draws WHERE issue=?", (issue,)).fetchone()
    with local_model_lock():
        scorer = LayaScorer(resolve_checkpoint(DATASET, manifest), manifest["trained_through_issue"])
        ranked = [{**row, "score": scorer.score(row["state"], issue)} for row in states]
    chosen = choose_candidate(ranked)
    result = None
    if draw:
        fh, bh = count_hits(chosen["front"], chosen["back"], decode(draw["front"]), decode(draw["back"]))
        level, amount = PRIZE_TABLE.get((fh, bh), (None, 0))
        result = {"front_hit": fh, "back_hit": bh, "level": level, "amount": amount}
    decision = {
        "issue": issue, "selected_model": chosen["model"],
        "label": MODEL_LABELS[chosen["model"]], "front": chosen["front"], "back": chosen["back"],
        "score": round(chosen["score"], 6), "model_version": manifest["version"],
        "candidate_scores": [{"model": row["model"], "score": round(row["score"], 6)} for row in ranked],
        "trained_through_issue": manifest["trained_through_issue"],
        "kind": "retrospective" if draw else "prospective", "result": result,
    }
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    decisions = [d for d in report.get("decisions", []) if d["issue"] != issue]
    decisions.append(decision)
    decisions.sort(key=lambda d: d["issue"], reverse=True)
    write_report(REPORT, {"decisions": decisions})
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description="Laya 独立决策实验（保留原 9 模型）")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build")
    train = commands.add_parser("train")
    train.add_argument("--version", required=True)
    train.add_argument("--split", choices=["train", "all"], default="train")
    train.add_argument("--epochs", type=int, default=4)
    train.add_argument("--max-items", type=int, default=0)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--version", required=True)
    selection = commands.add_parser("decide")
    selection.add_argument("--issue", required=True)
    selection.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.command == "build":
        with get_conn() as conn:
            result = build_dataset(conn, DATA_DIR.parent / "docs/RUN_LOG.jsonl", DATASET)
    elif args.command == "train":
        result = train_version(DATASET, args.version, split=args.split, epochs=args.epochs, max_items=args.max_items)
        if args.split == "all" and not args.max_items:
            write_report(REPORT, {"active_model": result, "trained_through_issue": result["trained_through_issue"]})
    else:
        manifest_path = DATASET / "manifests" / f"{args.version}.json"
        # Restrict manifests to the known dataset directory.
        if manifest_path.parent.resolve() != (DATASET / "manifests").resolve():
            raise ValueError("Invalid model version")
        manifest = json.loads(manifest_path.read_text())
        if args.command == "evaluate":
            with get_conn() as conn:
                result = evaluate_version(conn, DATASET, manifest, REPORT)
        else:
            result = decide(args.issue, manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
