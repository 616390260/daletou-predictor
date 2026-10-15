"""Regression coverage for source money columns and versioned prize rules."""
import importlib
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from backend.src.scraper.fetch_history import _parse_500_html


def _html():
    return ('<tr class="t_tr1"><td class="t_tr1">26014</td>'
            + ''.join(f'<td class="cfont2">{i}</td>' for i in range(1, 6))
            + '<td class="cfont4">6</td><td class="cfont4">7</td>'
            + '<td class="t_tr1">900,000,001</td><td>unused</td>'
            + '<td class="t_tr1">300,000,002</td><td class="t_tr1">2026-02-02</td></tr>')


@contextmanager
def _draw_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE draws (issue TEXT PRIMARY KEY, draw_date TEXT, front TEXT, back TEXT, sales INTEGER, pool INTEGER)')
    conn.execute("INSERT INTO draws VALUES ('26014', '2026-02-02', '01,02,03,04,05', '06,07', 0, 0)")
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


class DataRulesTests(unittest.TestCase):
    def test_500_money_columns_match_header_order(self):
        row, = _parse_500_html(_html())
        self.assertEqual(row['sales'], 300_000_002)
        self.assertEqual(row['pool'], 900_000_001)

    def test_2026_fixed_prizes_and_threshold(self):
        prizes = importlib.import_module('backend.src.utils.prizes')
        cases = [
            ((5, 0), '三等奖', 5000, 6666), ((4, 2), '三等奖', 5000, 6666),
            ((4, 1), '四等奖', 300, 380), ((4, 0), '五等奖', 150, 200),
            ((3, 2), '五等奖', 150, 200), ((3, 1), '六等奖', 15, 18),
            ((2, 2), '六等奖', 15, 18), ((3, 0), '七等奖', 5, 7),
            ((2, 1), '七等奖', 5, 7), ((1, 2), '七等奖', 5, 7),
            ((0, 2), '七等奖', 5, 7),
        ]
        for hits, level, low, high in cases:
            with self.subTest(hits=hits):
                self.assertEqual(prizes.prize_for_hits('26014', *hits, 799_999_999), (level, low))
                self.assertEqual(prizes.prize_for_hits('26014', *hits, 800_000_000), (level, high))
                self.assertEqual(prizes.prize_for_hits('27001', *hits, 900_000_000), (level, high))

    def test_legacy_prize_boundary_and_losing_hits(self):
        prizes = importlib.import_module('backend.src.utils.prizes')
        self.assertEqual(prizes.prize_for_hits('26013', 4, 2, 900_000_000), ('四等奖', 3000))
        self.assertEqual(prizes.prize_for_hits('26013', 5, 0), ('三等奖', 10000))
        self.assertEqual(prizes.prize_for_hits('26014', 1, 1), (None, 0))
        self.assertIn('估算', prizes.PRIZE_ESTIMATE_NOTE)

    def test_financial_repair_changes_only_money_and_is_idempotent(self):
        repair = importlib.import_module('backend.src.tasks.repair_financials')
        with _draw_db() as conn:
            records = _parse_500_html(_html())
            self.assertEqual(repair.repair_financials(conn, records)['updated_count'], 1)
            self.assertEqual(tuple(conn.execute('SELECT * FROM draws').fetchone()), (
                '26014', '2026-02-02', '01,02,03,04,05', '06,07', 300_000_002, 900_000_001))
            self.assertEqual(repair.repair_financials(conn, records)['updated_count'], 0)

    def test_financial_repair_rejects_identity_mismatch_before_any_update(self):
        repair = importlib.import_module('backend.src.tasks.repair_financials')
        for field, value in [('draw_date', '2026-02-03'), ('front', '01,02,03,04,06'), ('back', '06,08')]:
            with self.subTest(field=field), _draw_db() as conn:
                records = _parse_500_html(_html())
                records[0][field] = value
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    repair.repair_financials(conn, records)
                self.assertEqual(conn.execute('SELECT sales FROM draws').fetchone()[0], 0)

    def test_financial_repair_rejects_missing_or_duplicate_source(self):
        repair = importlib.import_module('backend.src.tasks.repair_financials')
        with _draw_db() as conn:
            with self.assertRaises(ValueError):
                repair.repair_financials(conn, [])
            with self.assertRaises(ValueError):
                repair.repair_financials(conn, _parse_500_html(_html()) * 2)

    def test_financial_repair_does_not_replace_money_with_empty_source(self):
        repair = importlib.import_module('backend.src.tasks.repair_financials')
        with _draw_db() as conn:
            records = _parse_500_html(_html())
            records[0]['sales'] = 0
            self.assertEqual(repair.repair_financials(conn, records)['updated_count'], 0)
            self.assertEqual(conn.execute('SELECT pool FROM draws').fetchone()[0], 0)

    def test_previous_pool_does_not_read_target_or_future(self):
        prizes = importlib.import_module('backend.src.utils.prizes')
        with _draw_db() as conn:
            conn.execute("UPDATE draws SET pool = 900000000")
            self.assertEqual(prizes.previous_pool(conn, '26014'), 0)
            self.assertEqual(prizes.previous_pool(conn, '26015'), 900000000)

    def test_evaluate_uses_previous_pool_and_new_issue_rule(self):
        from backend.src.tasks import evaluate
        with _draw_db() as conn:
            conn.executescript('''
                CREATE TABLE predictions (issue TEXT, model TEXT, ticket_idx INTEGER, front TEXT, back TEXT);
                CREATE TABLE results (issue TEXT, model TEXT, ticket_idx INTEGER, front_hit INTEGER,
                    back_hit INTEGER, prize_level TEXT, prize_amount INTEGER);
                INSERT INTO draws VALUES ('26013', '2026-01-31', '01,02,03,04,05', '06,07', 1, 799999999);
                UPDATE draws SET pool = 900000000 WHERE issue = '26014';
                INSERT INTO predictions VALUES ('26014', 'random', 0, '01,02,03,04,06', '06,07');
            ''')
            @contextmanager
            def get_conn():
                yield conn
            with patch.object(evaluate, 'get_conn', get_conn):
                self.assertEqual(evaluate.evaluate_issue('26014', notify_on_done=False), 1)
            self.assertEqual(tuple(conn.execute('SELECT prize_level, prize_amount FROM results').fetchone()), ('三等奖', 5000))

    def test_backtest_uses_new_rule_without_changing_tickets(self):
        from backend.src.tasks import backtest
        from backend.src.models.base import Ticket
        with _draw_db() as conn:
            conn.executescript('''
                CREATE TABLE predictions (issue TEXT, model TEXT, ticket_idx INTEGER, front TEXT, back TEXT);
                CREATE TABLE results (issue TEXT, model TEXT, ticket_idx INTEGER, front_hit INTEGER,
                    back_hit INTEGER, prize_level TEXT, prize_amount INTEGER);
                INSERT INTO draws VALUES ('26013', '2026-01-31', '01,02,03,04,05', '06,07', 1, 800000000);
            ''')
            @contextmanager
            def get_conn():
                yield conn
            history = pd.DataFrame([
                {'issue': f'{25001 + i:05d}', 'front': [1, 2, 3, 4, 5], 'back': [6, 7]}
                for i in range(99)
            ] + [{'issue': '26014', 'front': [1, 2, 3, 4, 5], 'back': [6, 7]}])
            model = Mock()
            model.predict.return_value = [Ticket(front=[1, 2, 3, 4, 6], back=[6, 7])]
            with patch.object(backtest, 'get_conn', get_conn), patch.object(backtest, 'init_db'), \
                    patch.object(backtest, 'load_history', return_value=history), \
                    patch.object(backtest, 'get_model', return_value=model), patch.object(backtest, '_write_state'):
                self.assertTrue(backtest.run_backtest(start_idx=-1, only=['random'])['done'])
            self.assertEqual(tuple(conn.execute('SELECT prize_level, prize_amount FROM results').fetchone()), ('三等奖', 6666))
            self.assertEqual(conn.execute('SELECT front FROM predictions').fetchone()[0], '01,02,03,04,06')

    def test_financial_repair_dry_run_keeps_database_unchanged(self):
        repair = importlib.import_module('backend.src.tasks.repair_financials')
        with _draw_db() as conn:
            result = repair.repair_financials(conn, _parse_500_html(_html()), apply=False)
            self.assertEqual(result['would_update_count'], 1)
            self.assertEqual(result['updated_count'], 0)
            self.assertEqual(conn.execute('SELECT sales FROM draws').fetchone()[0], 0)

    def test_run_audit_has_source_hash_and_applied_range(self):
        import hashlib
        import json
        repair = importlib.import_module('backend.src.tasks.repair_financials')
        with tempfile.TemporaryDirectory() as tmp, _draw_db() as conn:
            db_path = Path(tmp) / 'test.db'
            disk = sqlite3.connect(db_path)
            conn.backup(disk)
            disk.close()
            audit_path = Path(tmp) / 'audit.json'
            with patch.object(repair, '_fetch_500', return_value=_html()):
                audit = repair.run(db_path, audit_path, apply=True)
            self.assertEqual(audit['updated_count'], 1)
            self.assertEqual(audit['issue_start'], '26014')
            self.assertEqual(audit['issue_end'], '26014')
            self.assertEqual(audit['source_sha256'], hashlib.sha256(_html().encode()).hexdigest())
            self.assertEqual(json.loads(audit_path.read_text()), audit)

    def test_missing_official_money_does_not_erase_existing_values(self):
        from backend.src.scraper import fetch_history
        with _draw_db() as conn:
            conn.execute('UPDATE draws SET sales = 123, pool = 456')
            conn.commit()
            records = _parse_500_html(_html())
            records[0].update(sales=0, pool=0)
            @contextmanager
            def get_conn():
                yield conn
            with patch.object(fetch_history, 'get_conn', get_conn), patch.object(fetch_history, 'init_db'):
                fetch_history.save_to_db(records)
            self.assertEqual(tuple(conn.execute('SELECT sales, pool FROM draws').fetchone()), (123, 456))

    def test_old_money_feature_meta_is_rejected(self):
        for module_name in ['lstm_model', 'transformer_model']:
            with self.subTest(module=module_name), tempfile.TemporaryDirectory() as tmp:
                module = importlib.import_module('backend.src.models.' + module_name)
                meta_path = Path(tmp) / 'meta.json'
                meta_path.write_text('{"last_trained_issue":"26117"}')
                with patch.object(module, 'META_PATH', meta_path):
                    load = module._load_meta if module_name == 'lstm_model' else module.TransformerModel()._load_meta
                    self.assertEqual(load(), {})
                    from backend.src.config import MONEY_FEATURE_VERSION
                    meta_path.write_text('{"last_trained_issue":"26117","money_feature_version":' + str(MONEY_FEATURE_VERSION) + '}')
                    self.assertEqual(load()['last_trained_issue'], '26117')

    def test_xgboost_old_cache_is_retrained(self):
        import numpy as np
        module = importlib.import_module('backend.src.models.xgboost_model')
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / 'probs.npz'
            np.savez(cache_path, signature=np.array(['1-26117']), front_p=np.array([0.1]), back_p=np.array([0.2]))
            with patch.object(module, 'CACHE_PATH', cache_path):
                model = module.XGBoostModel()
                trainer = Mock(return_value=np.array([0.5]))
                with patch.object(model, '_train_predict', trainer):
                    history = pd.DataFrame([{'issue': '26117'}])
                    front, back = model._cached_probs(history)
                    self.assertEqual(trainer.call_count, 2)
                    self.assertEqual(front[0], 0.5)
                    self.assertEqual(back[0], 0.5)
                    model._cached_probs(history)
                    self.assertEqual(trainer.call_count, 2)


if __name__ == '__main__':
    unittest.main()
