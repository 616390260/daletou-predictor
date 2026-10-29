"""Regression coverage for immutable, prospective Laya decisions and settlement."""
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from backend.src.config import MODELS
from backend.src.laya import lifecycle


class LayaSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.report_path = self.root / 'laya.json'
        self.dataset = self.root / 'dataset'
        self.dataset.mkdir()
        (self.dataset / 'metadata.json').write_text(json.dumps({'verified_start_issue': '26059'}))
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript((Path(__file__).resolve().parents[1] / 'src/db/schema.sql').read_text())
        self.conn.execute("INSERT INTO draws(issue,draw_date,front,back,pool) VALUES('26123','2026-10-28','13,18,19,20,28','09,11',731643950)")
        for model in MODELS:
            self.conn.execute("INSERT INTO predictions(issue,model,ticket_idx,front,back,created_at) VALUES('26124',?,0,'01,02,03,04,05','01,02','2026-10-28 13:43:00')", (model,))
        self.conn.commit()
        self.frozen = {'evaluation': {'version': 'frozen', 'issues': 10},
                       'dataset': {'dataset_sha256': 'frozen'}, 'decisions': []}
        self.report_path.write_text(json.dumps(self.frozen))
        self.manifest = {'version': 'daletou-decision-v1', 'trained_through_issue': '26116'}
        self.now = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
        self.clock = patch.object(lifecycle, '_now', return_value=self.now)
        self.clock.start()
        self.scorer = Mock()
        self.scorer.score.side_effect = lambda state, issue: 0.8 if json.loads(state)['model'] == 'genetic' else 0.1
        self.factory = Mock(return_value=self.scorer)

    def tearDown(self):
        self.clock.stop()
        self.conn.close()
        self.temp.cleanup()

    def decide(self):
        return lifecycle.create_decision(self.conn, '26124', self.manifest, self.dataset,
                                         self.report_path, scorer_factory=self.factory)

    def test_creates_next_issue_only_from_existing_candidates_without_modifying_db(self):
        original = self.conn.iterdump()
        before = '\n'.join(original)
        decision = self.decide()
        self.assertEqual(decision['selected_model'], 'genetic')
        self.assertEqual(decision['kind'], 'prospective')
        self.assertEqual(decision['trained_through_issue'], '26116')
        self.assertIsNone(decision['result'])
        self.assertEqual(len(decision['candidate_scores']), 9)
        self.assertEqual(before, '\n'.join(self.conn.iterdump()))
        report = json.loads(self.report_path.read_text())
        self.assertEqual(report['evaluation'], self.frozen['evaluation'])
        self.assertEqual(report['dataset'], self.frozen['dataset'])

    def test_existing_decision_is_immutable_and_does_not_load_model(self):
        decision = self.decide()
        before = self.report_path.read_bytes()
        self.factory.reset_mock()
        self.assertEqual(self.decide(), decision)
        self.factory.assert_not_called()
        self.assertEqual(self.report_path.read_bytes(), before)

    def test_drawn_or_non_next_issue_is_rejected_before_loading_model(self):
        for issue in ('26123', '26125'):
            with self.subTest(issue=issue), self.assertRaisesRegex(ValueError, 'next|drawn'):
                lifecycle.create_decision(self.conn, issue, self.manifest, self.dataset,
                                          self.report_path, scorer_factory=self.factory)
        self.factory.assert_not_called()

    def test_missing_candidate_skips_preflight_and_prevents_selection(self):
        self.conn.execute("DELETE FROM predictions WHERE model='ensemble'")
        status = lifecycle.inspect_sync(self.conn, json.loads(self.report_path.read_text()), self.now)
        self.assertFalse(status['needs_decision'])
        self.assertEqual(status['reason'], 'missing_candidates')
        with self.assertRaisesRegex(ValueError, 'candidate'):
            self.decide()
        self.factory.assert_not_called()

    def test_deadline_is_checked_before_and_after_scoring(self):
        deadline = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        before = self.report_path.read_bytes()
        with patch.object(lifecycle, '_now', return_value=deadline):
            with self.assertRaisesRegex(ValueError, 'deadline'):
                self.decide()
        self.factory.assert_not_called()
        with patch.object(lifecycle, '_now', side_effect=[self.now, deadline]):
            with self.assertRaisesRegex(ValueError, 'deadline'):
                self.decide()
        self.assertEqual(self.report_path.read_bytes(), before)

    def test_candidate_change_during_scoring_is_rejected(self):
        def change(state, issue):
            self.conn.execute("UPDATE predictions SET front='06,07,08,09,10' WHERE model='random'")
            return 0.5
        self.scorer.score.side_effect = change
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.decide()
        self.assertEqual(json.loads(self.report_path.read_text()), self.frozen)

    def test_scorer_cannot_use_target_or_future_training_checkpoint(self):
        self.manifest['trained_through_issue'] = '26124'
        with self.assertRaisesRegex(ValueError, 'cutoff'):
            self.decide()
        self.factory.assert_not_called()

    def test_settlement_keeps_frozen_choice_and_uses_current_prize_rule(self):
        d = self.decide()
        selected = copy.deepcopy(d)
        self.conn.execute("INSERT INTO draws(issue,draw_date,front,back) VALUES('26124','2026-10-31','01,02,20,21,22','01,10')")
        self.conn.commit()
        self.assertEqual(lifecycle.settle_saved(self.conn, self.report_path), 1)
        report = json.loads(self.report_path.read_text())
        settled = report['decisions'][0]
        for key, value in selected.items():
            if key != 'result':
                self.assertEqual(settled[key], value, key)
        self.assertEqual(settled['result']['front_hit'], 2)
        self.assertEqual(settled['result']['back_hit'], 1)
        self.assertEqual(settled['result']['level'], '七等奖')
        self.assertEqual(settled['result']['amount'], 5)
        self.assertEqual(report['evaluation'], self.frozen['evaluation'])
        before = self.report_path.read_bytes()
        self.assertEqual(lifecycle.settle_saved(self.conn, self.report_path), 0)
        self.assertEqual(self.report_path.read_bytes(), before)

    def test_preflight_does_not_backfill_expired_undrawn_target(self):
        late = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)
        status = lifecycle.inspect_sync(self.conn, self.frozen, late)
        self.assertFalse(status['needs_decision'])
        self.assertEqual(status['reason'], 'deadline_passed')

    def test_check_cli_is_read_only_and_emits_machine_readable_outputs(self):
        from backend.src.tasks import laya_sync
        report = {**self.frozen, 'active_model': {'version': self.manifest['version']}}
        self.report_path.write_text(json.dumps(report))
        before = self.report_path.read_bytes()
        output = self.root / 'github-output'
        @contextmanager
        def connection():
            yield self.conn
        with patch.object(laya_sync, 'get_conn', connection), \
                patch.object(laya_sync, 'REPORT', self.report_path), \
                patch.object(laya_sync, 'datetime') as clock, \
                patch.dict('os.environ', {'GITHUB_OUTPUT': str(output)}), \
                patch('sys.argv', ['laya_sync', '--check']), redirect_stdout(io.StringIO()):
            clock.now.return_value = self.now
            laya_sync.main()
        self.assertEqual(self.report_path.read_bytes(), before)
        self.assertIn('needs_decision=true\n', output.read_text())
        self.assertIn('issue=26124\n', output.read_text())
        self.assertIn('version=daletou-decision-v1\n', output.read_text())

    def test_settle_only_cli_needs_no_active_checkpoint_or_scorer(self):
        from backend.src.tasks import laya_sync
        @contextmanager
        def connection():
            yield self.conn
        with patch.object(laya_sync, 'get_conn', connection), \
                patch.object(laya_sync, 'REPORT', self.report_path), \
                patch.object(laya_sync, 'create_decision') as create, \
                patch('sys.argv', ['laya_sync', '--settle-only']), redirect_stdout(io.StringIO()):
            laya_sync.main()
        create.assert_not_called()
        self.assertEqual(json.loads(self.report_path.read_text()), self.frozen)


if __name__ == '__main__':
    unittest.main()
