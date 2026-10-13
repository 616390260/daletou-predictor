"""Independent evaluation and report persistence tests."""
import json
import tempfile
import unittest
import hashlib
import sqlite3
from unittest.mock import patch
from pathlib import Path

from backend.src.laya.experiment import evaluate_rows, write_report, resolve_checkpoint, _recheck_rows


class Scorer:
    def __init__(self):
        self.seen = []

    def score(self, state, issue):
        self.seen.append((state, issue))
        return {"first": 0.2, "second": 0.7}[state]


class LayaExperimentTests(unittest.TestCase):
    def test_checkpoint_restores_portable_head_and_rejects_changed_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset"
            adapters = dataset / "adapters"
            adapters.mkdir(parents=True)
            version = "daletou-test"
            (adapters / f"{version}.safetensors").write_bytes(b"head")
            config = {"version": version, "trained_through_issue": "26098", "source_sha256": "source"}
            (adapters / f"{version}.json").write_text(json.dumps(config))
            manifest = {**config, "checkpoint_sha256": hashlib.sha256(b"head").hexdigest()}
            with patch("backend.src.laya.experiment.LAYA_HOME", root / "laya-lab"):
                path = resolve_checkpoint(dataset, manifest)
                self.assertEqual((path / "model.safetensors").read_bytes(), b"head")
                (path / "model.safetensors").write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "digest"):
                    resolve_checkpoint(dataset, manifest)

    def test_recheck_rejects_label_inconsistent_with_real_draw(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE draws(issue,front,back)")
        conn.execute("INSERT INTO draws VALUES ('26116','09,18,22,25,35','01,10')")
        row = {"id": "26116:random", "issue": "26116", "front": [1, 2, 3, 4, 5],
               "back": [2, 3], "result": {"front_hit": 0, "back_hit": 0, "level": None, "amount": 0},
               "label": "A", "probs": {"A": 1.0, "B": 0.0}}
        with self.assertRaisesRegex(ValueError, "label"):
            _recheck_rows(conn, [row])
        conn.close()

    def test_evaluation_scores_only_input_and_counts_one_ticket_per_issue(self):
        rows = []
        for issue in ["26115", "26116"]:
            for model, state, amount in [("random", "first", 0), ("frequency", "second", 5)]:
                rows.append({
                    "issue": issue, "model": model, "state": state,
                    "front": [1, 2, 3, 4, 5], "back": [1, 2],
                    "probs": {"A": float(amount > 0), "B": float(amount == 0)},
                    "result": {"front_hit": 2, "back_hit": 1, "level": None, "amount": amount},
                })
        scorer = Scorer()
        report = evaluate_rows(rows, scorer, train_win_rate=0.5)
        self.assertEqual(len(scorer.seen), 4)
        self.assertEqual(report["issues"], 2)
        self.assertEqual(report["tickets"], 2)
        self.assertEqual(report["wins"], 2)
        self.assertEqual(report["prize"], 10)
        self.assertEqual(report["cost"], 4)
        self.assertEqual([d["selected_model"] for d in report["decisions"]], ["frequency"] * 2)
        self.assertFalse(report["promotion_eligible"])

    def test_publishing_evaluation_preserves_separate_deployment_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "laya.json"
            path.write_text(json.dumps({"active_model": {"version": "production"}}))
            write_report(path, {"evaluation": {"version": "frozen"}})
            report = json.loads(path.read_text())
            self.assertEqual(report["active_model"]["version"], "production")
            self.assertEqual(report["evaluation"]["version"], "frozen")


if __name__ == "__main__":
    unittest.main()
