"""Time-boundary and input validation tests for the independent Laya layer."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.src.config import MODELS
from backend.src.laya.dataset import TASK, build_dataset, build_state
from backend.src.laya.runtime import LayaScorer, choose_candidate, validate_model_cutoff


class LayaDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        schema = Path(__file__).resolve().parents[1] / "src/db/schema.sql"
        self.conn.executescript(schema.read_text())
        for number in range(1, 13):
            issue = f"260{number:02}"
            self.conn.execute(
                "INSERT INTO draws(issue,draw_date,front,back) VALUES(?,?,?,?)",
                (issue, "2026-01-01", "01,02,03,04,05", "01,02"),
            )
            for model in MODELS:
                self.conn.execute(
                    "INSERT INTO predictions(issue,model,ticket_idx,front,back) VALUES(?,?,0,?,?)",
                    (issue, model, "01,02,03,04,05", "01,02"),
                )
                self.conn.execute(
                    "INSERT INTO results(issue,model,ticket_idx,front_hit,back_hit,prize_level,prize_amount) VALUES(?,?,0,5,2,'一等奖',10000000)",
                    (issue, model),
                )
        self.conn.commit()
        self.log = self.root / "RUN_LOG.jsonl"
        self.log.write_text(json.dumps({"outcome": "success", "extra": {
            "recovery": True, "historical_simulation": True,
            "start_issue": "26002", "end_issue": "26012",
        }}) + "\n")

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_state_excludes_target_and_future_outcomes(self):
        args = (self.conn, "26006", "random", [1, 2, 3, 4, 5], [1, 2], "26002")
        before = build_state(*args)
        self.conn.execute("UPDATE draws SET front='20,21,22,23,24',back='10,11' WHERE issue >= '26006'")
        self.conn.execute("UPDATE results SET front_hit=0,back_hit=0,prize_amount=0 WHERE issue >= '26006'")
        self.conn.commit()
        self.assertEqual(before, build_state(*args))

    def test_splits_keep_each_issue_together_and_in_order(self):
        meta = build_dataset(self.conn, self.log, self.root / "dataset")
        sets = {}
        for split in ("train", "validation", "test"):
            rows = [json.loads(line) for line in (self.root / "dataset" / f"{split}.jsonl").read_text().splitlines()]
            sets[split] = {r["issue"] for r in rows}
            self.assertEqual(len(rows), len(sets[split]) * len(MODELS))
            self.assertTrue(all(r["probs"] == {"A": 1.0, "B": 0.0} for r in rows))
        self.assertEqual(meta["issues"], 11)
        self.assertNotIn("26001", set.union(*sets.values()))
        self.assertLess(max(sets["train"]), min(sets["validation"]))
        self.assertLess(max(sets["validation"]), min(sets["test"]))
        self.assertFalse(sets["train"] & sets["test"])

    def test_missing_model_fails_instead_of_partial_training(self):
        self.conn.execute("DELETE FROM predictions WHERE issue='26005' AND model='ensemble'")
        with self.assertRaisesRegex(ValueError, "26005"):
            build_dataset(self.conn, self.log, self.root / "dataset")

    def test_no_verified_provenance_is_an_error(self):
        self.log.write_text('{"outcome":"success"}\n')
        with self.assertRaisesRegex(ValueError, "verified"):
            build_dataset(self.conn, self.log, self.root / "dataset")

    def test_invalid_candidate_does_not_enter_state(self):
        with self.assertRaises(ValueError):
            build_state(self.conn, "26006", "random", [1, 1, 2, 3, 4], [1, 2], "26002")

    def test_result_mismatch_fails_with_issue(self):
        self.conn.execute("UPDATE results SET front_hit=0 WHERE issue='26005' AND model='random'")
        with self.assertRaisesRegex(ValueError, "26005"):
            build_dataset(self.conn, self.log, self.root / "dataset")

    def _move_fixture_to_new_rule_issues(self):
        for table in ("draws", "predictions", "results"):
            self.conn.execute(f"UPDATE {table} SET issue=CAST(CAST(issue AS INTEGER)+20 AS TEXT)")
        self.conn.execute("UPDATE draws SET pool=800000000")
        self.conn.execute("UPDATE predictions SET front='01,02,03,04,06'")
        self.conn.execute("UPDATE results SET front_hit=4,back_hit=2,prize_level='四等奖',prize_amount=3000")
        self.conn.commit()
        self.log.write_text(json.dumps({"outcome": "success", "extra": {
            "recovery": True, "historical_simulation": True,
            "start_issue": "26022", "end_issue": "26032",
        }}) + "\n")

    def test_new_rule_results_preserve_frozen_v1_dataset_digest(self):
        self._move_fixture_to_new_rule_issues()
        legacy = build_dataset(self.conn, self.log, self.root / "legacy")
        self.conn.execute("UPDATE results SET prize_level='三等奖',prize_amount=6666")
        current = build_dataset(self.conn, self.log, self.root / "current")
        self.assertEqual(current['feature_version'], legacy['feature_version'])
        self.assertEqual(current['dataset_sha256'], legacy['dataset_sha256'])
        self.assertEqual((self.root / "current/all.jsonl").read_bytes(),
                         (self.root / "legacy/all.jsonl").read_bytes())
        row = json.loads((self.root / "current/all.jsonl").read_text().splitlines()[0])
        self.assertEqual(row['result']['level'], '四等奖')
        self.assertEqual(row['result']['amount'], 3000)

    def test_new_rule_results_reject_corrupt_amount_even_if_still_winning(self):
        self._move_fixture_to_new_rule_issues()
        self.conn.execute("UPDATE results SET prize_level='三等奖',prize_amount=6666")
        self.conn.execute("UPDATE results SET prize_amount=6667 WHERE issue='26025' AND model='random'")
        with self.assertRaisesRegex(ValueError, "26025.*random"):
            build_dataset(self.conn, self.log, self.root / "dataset")

    def test_new_rule_results_require_exact_independent_hits(self):
        self._move_fixture_to_new_rule_issues()
        self.conn.execute("UPDATE results SET prize_level='三等奖',prize_amount=6666")
        self.conn.execute("UPDATE results SET front_hit=5 WHERE issue='26022' AND model='random'")
        with self.assertRaisesRegex(ValueError, "26022.*random"):
            build_dataset(self.conn, self.log, self.root / "dataset")

    def test_unverified_results_do_not_change_history_features(self):
        args = (self.conn, "26006", "random", [1, 2, 3, 4, 5], [1, 2], "26002")
        before = build_state(*args)
        self.conn.execute("UPDATE results SET front_hit=0,back_hit=0,prize_amount=0 WHERE issue < '26002'")
        self.assertEqual(before, build_state(*args))

    def test_candidate_requires_exact_integer_counts(self):
        for front in ([1, 2, 3, 4, 5, 5], [1.0, 2, 3, 4, 5], [True, 2, 3, 4, 5]):
            with self.assertRaises(ValueError):
                build_state(self.conn, "26006", "random", front, [1, 2], "26002")

    def test_overlapping_ranges_are_deduplicated(self):
        record = {"outcome": "success", "extra": {
            "recovery": True, "historical_simulation": True,
            "start_issue": "26004", "end_issue": "26008",
        }}
        with self.log.open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        meta = build_dataset(self.conn, self.log, self.root / "dataset")
        self.assertEqual(meta["issues"], 11)
        self.assertEqual(meta["tickets"], 99)

    def test_too_few_verified_issues_are_rejected(self):
        self.conn.execute("DELETE FROM draws WHERE issue >= '26007'")
        with self.assertRaisesRegex(ValueError, "6 verified"):
            build_dataset(self.conn, self.log, self.root / "dataset")

    def test_frozen_evaluation_preserves_current_decision_and_deployment_model(self):
        import hashlib
        import types
        from contextlib import nullcontext
        from backend.src.laya.experiment import evaluate_version
        dataset = self.root / "dataset"
        meta = build_dataset(self.conn, self.log, dataset)
        manifest = {"version": "daletou-evaluation-test", "source_split": "train",
                    "source_sha256": hashlib.sha256((dataset / "train.jsonl").read_bytes()).hexdigest(),
                    "source_samples": meta["split_counts"]["train"],
                    "trained_through_issue": meta["cutoffs"]["train"]["last_issue"]}
        report_path = self.root / "laya.json"
        current = {"issue": "26117", "kind": "prospective"}
        report_path.write_text(json.dumps({"active_model": {"version": "deployment"}, "decisions": [current]}))
        scorer = types.SimpleNamespace(score=lambda state, issue: 0.3)
        with patch("backend.src.laya.experiment.local_model_lock", nullcontext), \
                patch("backend.src.laya.experiment.resolve_checkpoint", return_value=dataset), \
                patch("backend.src.laya.experiment.LayaScorer", return_value=scorer):
            report = evaluate_version(self.conn, dataset, manifest, report_path)
            self.assertEqual(report["active_model"]["version"], "deployment")
            self.assertIn(current, report["decisions"])
            self.assertTrue(all(d["kind"] == "heldout" for d in report["evaluation"]["decisions"]))
            with (dataset / "test.jsonl").open("a") as stream:
                stream.write((dataset / "test.jsonl").read_text().splitlines()[0] + "\n")
            with self.assertRaisesRegex(ValueError, "partitions"):
                evaluate_version(self.conn, dataset, manifest, report_path)


class LayaDecisionTests(unittest.TestCase):
    def test_future_trained_model_cannot_score_past_target(self):
        with self.assertRaisesRegex(ValueError, "cutoff"):
            validate_model_cutoff("26116", "26116")
        validate_model_cutoff("26116", "26117")

    def test_invalid_scores_are_rejected(self):
        for score in [float("nan"), float("inf"), -0.1, 1.1]:
            with self.assertRaises(ValueError):
                choose_candidate([{"model": "random", "score": score}])

    def test_highest_score_selects_existing_candidate(self):
        first = {"model": "random", "score": 0.2, "front": [1, 2, 3, 4, 5]}
        second = {"model": "frequency", "score": 0.7, "front": [6, 7, 8, 9, 10]}
        self.assertEqual(choose_candidate([first, second]), second)

    def test_equal_scores_follow_model_order_and_preserve_identity(self):
        first = {"model": "frequency", "score": 0.2}
        second = {"model": "random", "score": 0.2}
        self.assertIs(choose_candidate([first, second]), second)

    def test_empty_candidates_rejected(self):
        with self.assertRaises(ValueError):
            choose_candidate([])


class LayaRuntimeTests(unittest.TestCase):
    def setUp(self):
        import os
        self.env_patch = patch.dict(os.environ)
        self.env_patch.start()
        os.environ.pop("LAYA_DEVICE", None)
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.model = self.home / "laya-lab/models/daletou-test"
        self.model.mkdir(parents=True)
        self.config = self.model / "rl_agent_config.json"
        self.config.write_text(json.dumps({"task": TASK}), encoding="utf-8")
        self.home_patch = patch("backend.src.laya.runtime.Path.home", return_value=self.home)
        self.home_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.home_patch.stop()
        self.temp.cleanup()

    def test_seo_model_path_is_rejected_before_loading(self):
        with self.assertRaisesRegex(ValueError, "daletou"):
            LayaScorer(self.model.parent / "seo-keyword", "26098")

    def test_seo_task_in_allowed_path_is_rejected(self):
        self.config.write_text(json.dumps({"task": {**TASK, "name": "seo-keyword"}}))
        with self.assertRaisesRegex(ValueError, "daletou-decision"):
            LayaScorer(self.model, "26098")

    def test_symlink_outside_model_root_is_rejected(self):
        outside = self.home / "outside"
        outside.mkdir()
        link = self.model.parent / "daletou-link"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "daletou"):
            LayaScorer(link, "26098")

    def test_cutoff_is_checked_before_lazy_agent_import(self):
        scorer = LayaScorer(self.model, "26098")
        with self.assertRaisesRegex(ValueError, "cutoff"):
            scorer.score("{}", "26098")
        self.assertIsNone(scorer._agent)

    def test_laya_is_lazy_offline_and_uses_daletou_question(self):
        import os
        import types
        calls = []

        class Agent:
            def __init__(self, path, device):
                calls.append((path, device, os.environ["HF_HUB_OFFLINE"], os.environ["USE_TF"]))

            def predict(self, state, questions):
                self.asserted_question = questions
                calls.append((state, questions))
                return {"answers": {"s": {"probabilities": {"A": 0.25, "B": 0.75}}}}

        scorer = LayaScorer(self.model, "26098")
        self.assertEqual(calls, [])
        with patch.dict("sys.modules", {"laya": types.SimpleNamespace(Agent=Agent)}), patch.dict(os.environ):
            self.assertEqual(scorer.score("{}", "26099"), 0.25)
        self.assertEqual(calls[0], (str(self.model.resolve()), "mps", "1", "0"))
        self.assertEqual(calls[1][1], {"s": TASK["question"]})

    def test_invalid_probability_answers_are_rejected(self):
        import types
        scorer = LayaScorer(self.model, "26098")
        for probabilities in ({"A": 0.8, "B": 0.8}, {"A": float("nan"), "B": 0.5},
                              {"A": 1.1, "B": -0.1}, {"A": 1.0}, {"A": 0.5, "B": 0.5, "C": 0.0}):
            scorer._agent = types.SimpleNamespace(predict=lambda state, question: {
                "answers": {"s": {"probabilities": probabilities}},
            })
            with self.subTest(probabilities=probabilities), self.assertRaises(ValueError):
                scorer.score("{}", "26099")

    def test_explicit_cpu_device_is_used_for_lazy_inference(self):
        import os
        import types
        calls = []

        class Agent:
            def __init__(self, path, device):
                calls.append(device)

            def predict(self, state, questions):
                return {"answers": {"s": {"probabilities": {"A": 0.25, "B": 0.75}}}}

        with patch.dict(os.environ, {"LAYA_DEVICE": "cpu"}), \
                patch.dict("sys.modules", {"laya": types.SimpleNamespace(Agent=Agent)}):
            scorer = LayaScorer(self.model, "26098")
            self.assertEqual(scorer.score("{}", "26099"), 0.25)
        self.assertEqual(calls, ["cpu"])

    def test_invalid_device_is_rejected_before_import(self):
        import os
        for device in ("", "gpu", "cuda:0", "CPU", "cpu;echo invalid"):
            with self.subTest(device=device), patch.dict(os.environ, {"LAYA_DEVICE": device}):
                with self.assertRaisesRegex(ValueError, "LAYA_DEVICE"):
                    LayaScorer(self.model, "26098")

    def test_supported_device_selection(self):
        import os
        for device in ("cpu", "mps", "cuda"):
            with self.subTest(device=device), patch.dict(os.environ, {"LAYA_DEVICE": device}):
                self.assertEqual(LayaScorer(self.model, "26098").device, device)

    def test_adapter_cannot_load_seo_or_external_base(self):
        self.config.write_text(json.dumps({"task": TASK, "adapter_type": "head-only",
                                          "base_model_path": str(self.home / "seo")}))
        with self.assertRaisesRegex(ValueError, "base"):
            LayaScorer(self.model, "26098")

    def test_unknown_adapter_format_is_rejected(self):
        self.config.write_text(json.dumps({"task": TASK, "adapter_type": "other"}))
        with self.assertRaisesRegex(ValueError, "adapter"):
            LayaScorer(self.model, "26098")

    def test_head_adapter_restores_only_head_and_calibration(self):
        import hashlib
        import os
        import types
        base = self.home / "laya-lab/hf/hub/models--convaiinnovations--laya-multilingual/snapshots/base"
        base.mkdir(parents=True)
        (base / "model.safetensors").write_bytes(b"base")
        self.config.write_text(json.dumps({
            "task": TASK, "adapter_type": "head-only", "base_model_path": str(base),
            "base_checkpoint_sha256": hashlib.sha256(b"base").hexdigest(),
            "temperature": [1.0, 2.0, 1.0], "trained_through_issue": "26098",
        }))
        calls = []
        devices = []

        class Model:
            def state_dict(self):
                return {"encoder.weight": 1, "head.weight": 2}

            def load_state_dict(self, weights, strict):
                calls.append((weights, strict))

            def eval(self):
                pass

        class Agent:
            def __init__(self, path, device):
                devices.append(device)
                self.model = Model()

            def predict(self, state, questions):
                return {"answers": {"s": {"probabilities": {"A": 0.3, "B": 0.7}}}}

        modules = {"laya": types.SimpleNamespace(Agent=Agent),
                   "laya.common": types.SimpleNamespace(clamp_temperature=lambda x: x),
                   "safetensors.torch": types.SimpleNamespace(load_file=lambda path: {"head.weight": 5})}
        with patch.dict("sys.modules", modules), patch.dict(os.environ, {"LAYA_DEVICE": "cpu"}):
            scorer = LayaScorer(self.model, "26098")
            self.assertEqual(scorer.score("{}", "26099"), 0.3)
            self.assertEqual(calls, [({"head.weight": 5}, False)])
            self.assertEqual(scorer._agent.temperature, [1.0, 2.0, 1.0])
            self.assertEqual(scorer._agent.temperature_by_options, {})
            self.assertEqual(devices, ["cpu"])
            modules["safetensors.torch"].load_file = lambda path: {"encoder.weight": 5}
            with self.assertRaisesRegex(ValueError, "exactly"):
                LayaScorer(self.model, "26098").score("{}", "26099")


if __name__ == "__main__":
    unittest.main()
