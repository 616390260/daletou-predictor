"""Test finite-population statistics and verified, one-ticket-per-issue scope."""
import math
import tempfile
import unittest
from pathlib import Path
import json
import sqlite3
from unittest.mock import patch

from backend.src.analytics.significance import hit_distribution, exact_hit_test, holm_adjust, _collect_per_model_hits


class SignificanceTests(unittest.TestCase):
    def test_draw_hits_follow_sampling_without_replacement(self):
        pmf = hit_distribution(1, 35, 5)
        self.assertAlmostEqual(sum(pmf), 1)
        self.assertAlmostEqual(pmf[5], 1 / math.comb(35, 5))
        mean = sum(i * p for i, p in enumerate(pmf))
        variance = sum((i - mean) ** 2 * p for i, p in enumerate(pmf))
        self.assertAlmostEqual(mean, 5 * 5 / 35)
        self.assertAlmostEqual(variance, 5 * (5 / 35) * (30 / 35) * (30 / 34))

    def test_exact_test_convolves_whole_draws(self):
        self.assertAlmostEqual(exact_hit_test(2, 1, 4, 2), 1 / 3)
        self.assertAlmostEqual(exact_hit_test(0, 2, 4, 2), 1 / 18)

    def test_multiple_testing_correction_is_monotonic(self):
        values = holm_adjust([0.04, 0.001, 0.02])
        self.assertEqual(values, [0.04, 0.003, 0.04])

    def test_only_verified_or_pre_draw_logged_single_tickets_are_collected(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.executescript(Path('backend/src/db/schema.sql').read_text())
        for issue in ['26001', '26002', '26003', '26117']:
            conn.execute('INSERT INTO draws(issue,draw_date,front,back) VALUES(?,?,?,?)',
                         (issue, '2026-10-14', '01,02,03,04,05', '01,02'))
            for idx in [0, 1]:
                conn.execute('INSERT INTO predictions(issue,model,ticket_idx,front,back,created_at) VALUES(?,?,?,?,?,?)',
                             (issue, 'random', idx, '01,02,03,04,05', '01,02', '2026-10-14 03:00:00'))
                conn.execute('INSERT INTO results(issue,model,ticket_idx,front_hit,back_hit,prize_amount) VALUES(?,?,?,?,?,?)',
                             (issue, 'random', idx, 1, 0, 0))
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'RUN_LOG.jsonl'
            log.write_text('\n'.join(json.dumps(r) for r in [
                {'outcome': 'success', 'extra': {'recovery': True, 'historical_simulation': True, 'start_issue': '26002', 'end_issue': '26003'}},
                {'workflow': 'predict', 'outcome': 'success', 'ts': '2026-10-14T11:00:00+08:00', 'extra': {'predicted_issue': '26117'}},
            ]))
            with patch('backend.src.analytics.significance.get_conn', return_value=conn):
                stat = _collect_per_model_hits([log])['random']
                self.assertEqual(stat['issues'], {'26002', '26003', '26117'})
                self.assertEqual(stat['tickets'], 3)
                conn.execute("UPDATE predictions SET created_at='2026-10-14 13:00:00' WHERE issue='26117'")
                stat = _collect_per_model_hits([log])['random']
                self.assertEqual(stat['issues'], {'26002', '26003'})
        conn.close()


if __name__ == '__main__':
    unittest.main()
