"""Local training and frozen evaluation for the independent Laya decision layer."""
from __future__ import annotations

import fcntl
import hashlib
import json
import random
import re
import subprocess
import shutil
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..config import MODEL_LABELS, PRIZE_TABLE, TICKET_PRICE
from ..utils.numbers import count_hits, decode
from .runtime import LayaScorer, choose_candidate

LAYA_HOME = Path.home() / "laya-lab"


def read_rows(path: Path) -> list[dict]:
    """@returns Parsed JSONL records in source order."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def resolve_checkpoint(dataset: Path, manifest: dict) -> Path:
    """Restore a committed decision head if absent, then verify its version digest."""
    version = manifest["version"]
    if not re.fullmatch(r"daletou-[a-z0-9-]{1,60}", version):
        raise ValueError("Invalid checkpoint version")
    model = (LAYA_HOME / "models" / version).resolve()
    if model.parent != (LAYA_HOME / "models").resolve():
        raise ValueError("Invalid checkpoint path")
    if not model.exists():
        adapters = dataset / "adapters"
        source = adapters / f"{version}.safetensors"
        config = adapters / f"{version}.json"
        if not source.is_file() or not config.is_file():
            raise FileNotFoundError(f"Checkpoint {version} is unavailable locally and in the dataset")
        if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["checkpoint_sha256"]:
            raise ValueError("Committed checkpoint digest mismatch")
        model.mkdir(parents=True)
        shutil.copy2(source, model / "model.safetensors")
        shutil.copy2(config, model / "rl_agent_config.json")
    if hashlib.sha256((model / "model.safetensors").read_bytes()).hexdigest() != manifest["checkpoint_sha256"]:
        raise ValueError("Local checkpoint digest mismatch")
    config = json.loads((model / "rl_agent_config.json").read_text())
    for key in ("version", "trained_through_issue", "source_sha256"):
        if config.get(key) != manifest[key]:
            raise ValueError(f"Checkpoint metadata mismatch: {key}")
    return model


def write_report(path: Path, updates: dict) -> dict:
    """Merge report sections without overwriting the independently trained active model."""
    report = json.loads(path.read_text()) if path.exists() else {}
    report.update(updates)
    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    temporary.replace(path)
    return report


@contextmanager
def local_model_lock():
    """Respect the existing SEO Laya GPU lock while training or scoring."""
    with (LAYA_HOME / ".seo-laya.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another local Laya task is using the device") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def train_version(dataset: Path, version: str, *, split: str = "train",
                  epochs: int = 4, max_items: int = 0) -> dict:
    """Train a separate lottery checkpoint with the existing local trainer.

    @param split train for frozen evaluation, all for the deployment checkpoint.
    @returns Persisted manifest with the actual source cutoff and checkpoint digest.
    """
    if not re.fullmatch(r"daletou-[a-z0-9-]{1,60}", version):
        raise ValueError("Model version must start with daletou-")
    if split not in {"train", "all"} or not 1 <= epochs <= 20 or max_items < 0:
        raise ValueError("Invalid training parameters")
    source = dataset / f"{split}.jsonl"
    rows = read_rows(source)
    used = rows[:max_items] if max_items else rows
    if len(used) < 20:
        raise ValueError("At least 20 candidate samples are required")
    model_dir = LAYA_HOME / "models" / version
    if model_dir.exists():
        raise ValueError(f"Model already exists: {model_dir}")
    python = LAYA_HOME / ".venv/bin/python"
    trainer = LAYA_HOME / "train_local.py"
    if not python.is_file() or not trainer.is_file():
        raise FileNotFoundError("Local Laya environment or trainer is unavailable")
    args = [str(python), "-u", "-m", "backend.src.laya.train_head", str(dataset / "task.json"), str(source),
            str(model_dir), "--epochs", str(epochs)]
    if max_items:
        args += ["--max-items", str(max_items)]
    import os
    environment = {**os.environ, "USE_TF": "0", "HF_HUB_OFFLINE": "1",
                   "TRANSFORMERS_OFFLINE": "1", "HF_HOME": str(LAYA_HOME / "hf")}
    logs = dataset / "train_logs"
    logs.mkdir(exist_ok=True)
    started = time.monotonic()
    print(f"Training {version}: {len(used)} candidate samples, {epochs} epochs", flush=True)
    with local_model_lock(), (logs / f"{version}.log").open("w") as log:
        subprocess.run(args, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    checkpoint = model_dir / "model.safetensors"
    config = json.loads((model_dir / "rl_agent_config.json").read_text())
    if config.get("task", {}).get("name") != "daletou-decision" or not checkpoint.is_file():
        raise ValueError("Trainer did not produce the expected lottery checkpoint")
    digest = hashlib.sha256()
    with checkpoint.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    manifest = {
        "version": version, "model_path": f"~/laya-lab/models/{version}",
        "trained_through_issue": max(row["issue"] for row in used),
        "source_split": split, "source_samples": len(used), "epochs": epochs,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "checkpoint_sha256": digest.hexdigest(),
        "training_strategy": "head-only; shared multilingual encoder frozen",
        "base_checkpoint_sha256": config["base_checkpoint_sha256"],
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "calibration_policy": "Internal calibration uses only the training source; temporal holdouts remain independent",
    }
    config.update({key: manifest[key] for key in ("version", "trained_through_issue", "source_sha256")})
    (model_dir / "rl_agent_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2))
    manifests = dataset / "manifests"
    manifests.mkdir(exist_ok=True)
    (manifests / f"{version}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    if "smoke" not in version:
        adapters = dataset / "adapters"
        adapters.mkdir(exist_ok=True)
        shutil.copy2(checkpoint, adapters / f"{version}.safetensors")
        portable = {**config, "base_model_path": str(Path(config["base_model_path"]).relative_to(Path.home()))}
        portable["base_model_path"] = "~/" + portable["base_model_path"]
        (adapters / f"{version}.json").write_text(json.dumps(portable, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    return manifest


def _summary(decisions: list[dict]) -> dict:
    count = len(decisions)
    prize = sum(d["result"]["amount"] for d in decisions)
    cost = count * TICKET_PRICE
    return {"issues": count, "tickets": count,
            "wins": sum(d["result"]["amount"] > 0 for d in decisions),
            "cost": cost, "prize": prize, "roi": (prize - cost) / cost if cost else None}


def evaluate_rows(rows: list[dict], scorer, train_win_rate: float) -> dict:
    """Score inputs before consulting labels, selecting one existing ticket per issue."""
    if not rows:
        raise ValueError("No held-out candidates")
    groups: dict[str, list[dict]] = defaultdict(list)
    errors, baseline_errors = [], []
    for row in rows:
        score = scorer.score(row["state"], row["issue"])
        # Validate every score, including candidates that are not selected.
        choose_candidate([{**row, "score": score}])
        groups[row["issue"]].append({**row, "score": score})
        label = row["probs"]["A"]
        errors.append((score - label) ** 2)
        baseline_errors.append((train_win_rate - label) ** 2)
    decisions = []
    baselines: dict[str, list] = defaultdict(list)
    for issue, candidates in sorted(groups.items()):
        selected = choose_candidate(candidates)
        decisions.append({
            "issue": issue, "selected_model": selected["model"],
            "label": MODEL_LABELS.get(selected["model"], selected["model"]),
            "front": selected["front"], "back": selected["back"],
            "score": round(selected["score"], 6), "kind": "heldout",
            "candidate_scores": [{"model": row["model"], "score": round(row["score"], 6)}
                                 for row in candidates],
            "result": selected["result"],
        })
        baselines["random_selection"].append(random.Random(f"laya-baseline:{issue}").choice(candidates))
        for name in ["random", "ensemble"]:
            matches = [r for r in candidates if r["model"] == name]
            if matches:
                baselines[name].append(matches[0])
    return {
        **_summary(decisions), "brier": sum(errors) / len(errors),
        "constant_baseline_brier": sum(baseline_errors) / len(baseline_errors),
        "candidate_samples": len(rows), "train_win_rate": train_win_rate,
        "win_recall_at_half": sum(r["score"] >= 0.5 and r["probs"]["A"] == 1
                                  for group in groups.values() for r in group) / max(1, sum(r["probs"]["A"] for r in rows)),
        "baselines": {name: _summary(group) for name, group in baselines.items()},
        "promotion_eligible": False, "decisions": decisions,
    }


def _recheck_rows(conn, rows: list[dict]) -> None:
    """Independently recheck frozen labels against real draws without touching the DB."""
    for row in rows:
        draw = conn.execute("SELECT front,back FROM draws WHERE issue=?", (row["issue"],)).fetchone()
        if draw is None:
            raise ValueError(f"Missing real draw for {row['issue']}")
        fh, bh = count_hits(row["front"], row["back"], decode(draw["front"]), decode(draw["back"]))
        level, amount = PRIZE_TABLE.get((fh, bh), (None, 0))
        if row["result"] != {"front_hit": fh, "back_hit": bh, "level": level, "amount": amount}:
            raise ValueError(f"Frozen label mismatch: {row['id']}")
        won = amount > 0
        if row.get("label") != ("A" if won else "B") or row.get("probs") != {"A": float(won), "B": float(not won)}:
            raise ValueError(f"Frozen label/probability mismatch: {row['id']}")


def evaluate_version(conn, dataset: Path, manifest: dict, report_path: Path) -> dict:
    """Publish a frozen evaluation, never using the later deployment checkpoint."""
    if manifest["source_split"] != "train":
        raise ValueError("Evaluation requires a train-only checkpoint")
    source = dataset / "train.jsonl"
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["source_sha256"]:
        raise ValueError("Training snapshot changed after checkpoint creation")
    if "smoke" in manifest["version"]:
        raise ValueError("Smoke checkpoints cannot be published as formal evaluations")
    meta = json.loads((dataset / "metadata.json").read_text())
    train = read_rows(source)
    validation = read_rows(dataset / "validation.jsonl")
    test = read_rows(dataset / "test.jsonl")
    all_source = dataset / "all.jsonl"
    if hashlib.sha256(all_source.read_bytes()).hexdigest() != meta["dataset_sha256"]:
        raise ValueError("Full dataset snapshot digest mismatch")
    all_rows = read_rows(all_source)
    if train + validation + test != all_rows:
        raise ValueError("Temporal partitions must exactly reproduce the frozen dataset")
    for split, rows in (("train", train), ("validation", validation), ("test", test)):
        if sorted({r["issue"] for r in rows}) != meta["split_issues"][split]:
            raise ValueError(f"Changed temporal partition: {split}")
    if (manifest["source_samples"] != len(train)
            or manifest["trained_through_issue"] != max(r["issue"] for r in train)):
        raise ValueError("Evaluation checkpoint must use the complete frozen train partition")
    _recheck_rows(conn, all_rows)
    prior = sum(r["probs"]["A"] for r in train) / len(train)
    with local_model_lock():
        scorer = LayaScorer(resolve_checkpoint(dataset, manifest), manifest["trained_through_issue"])
        validation_result = evaluate_rows(validation, scorer, prior)
        evaluation = evaluate_rows(test, scorer, prior)
    decisions = evaluation.pop("decisions")
    for decision in decisions:
        decision.update(model_version=manifest["version"], trained_through_issue=manifest["trained_through_issue"])
    evaluation.update(model_version=manifest["version"], trained_through_issue=manifest["trained_through_issue"])
    evaluation["decisions"] = decisions
    evaluation["limitations"] = [
        "有效测试仅为按期分组的少量开奖记录，尚不足以证明稳定优势。",
        "Laya 评分不等同于可靠中奖概率，不自动干预原有 9 个模型。",
        "收益按项目统一固定奖金额估算，历史选票属于冻结回测。",
    ]
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    explicit = [d for d in report.get("decisions", []) if d.get("kind") != "heldout"]
    explicit_issues = {d["issue"] for d in explicit}
    visible = [d for d in decisions if d["issue"] not in explicit_issues] + explicit
    return write_report(report_path, {
        "status": "experimental", "label": "Laya 独立决策",
        "dataset": meta, "validation": validation_result,
        "evaluation": evaluation, "decisions": sorted(visible, key=lambda d: d["issue"], reverse=True),
    })
