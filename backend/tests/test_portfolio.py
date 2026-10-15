"""Independent checks of winning unions and immutable portfolio snapshots."""
import itertools
import math
import unittest
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.src.portfolio.coverage import Coverage, optimize
from backend.src.portfolio.service import create_portfolio, export_portfolios
from backend.src.config import MODELS


def brute(tickets, front_max=9, back_max=6):
    wins = 0
    for f in itertools.combinations(range(1, front_max + 1), 5):
        for b in itertools.combinations(range(1, back_max + 1), 2):
            wins += any(len(set(t['front']) & set(f)) >= 3
                        or len(set(t['back']) & set(b)) == 2
                        or (len(set(t['front']) & set(f)) == 2
                            and len(set(t['back']) & set(b)) >= 1) for t in tickets)
    return wins


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tickets = [dict(front=[1, 2, 3, 4, 5], back=[1, 2]),
                        dict(front=[1, 2, 6, 7, 8], back=[1, 2]),
                        dict(front=[3, 4, 7, 8, 9], back=[2, 3])]

    def test_union_matches_independent_exhaustive_draws(self):
        evaluator = Coverage([t['front'] for t in self.tickets], 9, 6)
        self.assertEqual(evaluator.count([t['back'] for t in self.tickets]), brute(self.tickets))
        self.assertEqual(evaluator.total, math.comb(9, 5) * math.comb(6, 2))

    def test_duplicate_tickets_do_not_add_coverage(self):
        t = self.tickets[0]
        one = Coverage([t['front']], 9, 6).count([t['back']])
        self.assertEqual(Coverage([t['front']] * 3, 9, 6).count([t['back']] * 3), one)

    def test_search_is_deterministic_and_cannot_reduce_coverage(self):
        a = optimize(self.tickets, front_max=9, back_max=6)
        self.assertEqual(a, optimize(self.tickets, front_max=9, back_max=6))
        self.assertGreaterEqual(a['optimized_count'], a['original_count'])
        self.assertEqual(a['optimized_count'], brute(a['tickets']))
        self.assertEqual([t['front'] for t in a['tickets']], [t['front'] for t in self.tickets])
        self.assertEqual(len(a['tickets']), len(self.tickets))

    def test_invalid_or_empty_tickets_fail_closed(self):
        for tickets in ([], [dict(front=[1, 1, 2, 3, 4], back=[1, 2])],
                        [dict(front=[1, 2, 3, 4, 36], back=[1, 2])],
                        [dict(front=[1, 2, 3, 4, 5], back=[1, 1])]):
            with self.assertRaises(ValueError):
                optimize(tickets)


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(Path('backend/src/db/schema.sql').read_text())
        self.conn.execute("INSERT INTO draws(issue,draw_date,front,back) VALUES('26117','2026-10-14','01,02,03,04,05','01,02')")
        for model in MODELS:
            self.conn.execute("INSERT INTO predictions(issue,model,ticket_idx,front,back) VALUES('26118',?,0,'01,02,03,04,05','01,02')", (model,))
        self.connection = patch('backend.src.portfolio.service.get_conn', return_value=self.conn)
        self.connection.start()
        self.clock = patch('backend.src.portfolio.service._now', return_value=datetime(2026, 10, 16, tzinfo=timezone.utc))
        self.clock.start()

    def tearDown(self):
        self.connection.stop()
        self.clock.stop()
        self.conn.close()

    def test_snapshot_is_idempotent_and_does_not_change_original_predictions(self):
        before = [tuple(r) for r in self.conn.execute('SELECT * FROM predictions')]
        first = create_portfolio('26118')
        self.assertEqual(first, create_portfolio('26118'))
        self.assertEqual(first['kind'], 'prospective')
        self.assertEqual(first['history_cutoff'], '26117')
        self.assertEqual(first['cost'], 18)
        self.assertEqual(before, [tuple(r) for r in self.conn.execute('SELECT * FROM predictions')])
        self.conn.execute("UPDATE predictions SET back='02,03' WHERE model='random'")
        with self.assertRaisesRegex(ValueError, 'changed'):
            create_portfolio('26118')

    def test_settlement_uses_saved_tickets_without_replacing_the_snapshot(self):
        first = create_portfolio('26118')
        self.conn.execute("INSERT INTO draws(issue,draw_date,front,back) VALUES('26118','2026-10-17','01,02,03,04,05','01,02')")
        with tempfile.TemporaryDirectory() as directory:
            with patch('backend.src.portfolio.service.EXPORT_DIR', Path(directory)):
                report = export_portfolios()
        run = report['runs'][0]
        self.assertEqual(run['tickets'], first['tickets'])
        self.assertEqual(run['created_at'], first['created_at'])
        self.assertTrue(run['result']['optimized']['any_win'])
        self.assertEqual(report['summary']['prospective']['periods'], 1)

    def test_rejects_past_or_unverified_simulations_and_missing_candidates(self):
        with self.assertRaises(ValueError):
            create_portfolio('26117')
        with self.assertRaises(ValueError):
            create_portfolio('26118', kind='historical_simulation')
        self.conn.execute("DELETE FROM predictions WHERE model='random'")
        with self.assertRaisesRegex(ValueError, 'nine'):
            create_portfolio('26118')

    def test_missing_draw_feed_cannot_turn_a_late_snapshot_into_a_prospective_prediction(self):
        with patch('backend.src.portfolio.service._now', return_value=datetime(2026, 10, 18, tzinfo=timezone.utc)):
            with self.assertRaisesRegex(ValueError, 'deadline'):
                create_portfolio('26118')

    def test_optimizer_finishing_after_deadline_cannot_publish_a_prospective_snapshot(self):
        times = [datetime(2026, 10, 17, 11, 59, 59, tzinfo=timezone.utc),
                 datetime(2026, 10, 17, 12, 0, 1, tzinfo=timezone.utc)]
        self.conn.commit()
        with patch('backend.src.portfolio.service._now', side_effect=times):
            with self.assertRaisesRegex(ValueError, 'deadline'):
                create_portfolio('26118')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM portfolio_runs').fetchone()[0], 0)

    def test_force_prediction_is_rejected_before_mutating_frozen_source_candidates(self):
        import pandas as pd
        from backend.src.tasks.predict import run_predict
        create_portfolio('26118')
        before = [tuple(r) for r in self.conn.execute('SELECT * FROM predictions')]
        with patch('backend.src.tasks.predict.get_conn', return_value=self.conn), \
                patch('backend.src.tasks.predict.init_db'), \
                patch('backend.src.tasks.predict.load_history', return_value=pd.DataFrame({'issue': ['26117'] * 50})), \
                patch('backend.src.tasks.predict.get_model') as model:
            with self.assertRaisesRegex(ValueError, '冻结'):
                run_predict('26118', force=True, notify_on_done=False)
            model.assert_not_called()
        self.assertEqual(before, [tuple(r) for r in self.conn.execute('SELECT * FROM predictions')])


if __name__ == '__main__':
    unittest.main()
