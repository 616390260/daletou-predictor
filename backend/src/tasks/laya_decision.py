"""CLI for local Laya training, frozen evaluation and independent candidate selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import DATA_DIR, EXPORT_DIR
from ..db import get_conn
from ..laya.dataset import build_dataset
from ..laya.experiment import evaluate_version, train_version, write_report
from ..laya.lifecycle import create_decision

DATASET = DATA_DIR / "laya"
REPORT = EXPORT_DIR / "laya.json"


def decide(issue: str, manifest: dict) -> dict:
    """Freeze a next-issue choice, preserving any already published decision."""
    with get_conn() as conn:
        return create_decision(conn, issue, manifest, DATASET, REPORT)


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
