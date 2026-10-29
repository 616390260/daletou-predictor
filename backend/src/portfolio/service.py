"""Persist independent portfolios and report prospective results separately."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ..analytics.significance import _collect_per_model_hits
from ..config import EXPORT_DIR, MODELS, TICKET_PRICE
from ..db import get_conn
from ..utils.draw_calendar import next_draw_deadline as _deadline
from ..utils.numbers import decode
from .coverage import VERSION, optimize


def _now():
    return datetime.now(timezone.utc)


def verified_issues():
    """@returns Shared verified issue set for all nine original models."""
    stats = _collect_per_model_hits()
    if any(m not in stats for m in MODELS):
        return set()
    return set.intersection(*(stats[m]['issues'] for m in MODELS))


def assert_candidates_mutable(issue):
    """Reject force before any model writes when an independent snapshot is frozen."""
    with get_conn() as conn:
        if conn.execute('SELECT 1 FROM portfolio_runs WHERE issue=? LIMIT 1', (issue,)).fetchone():
            raise ValueError('本期覆盖快照已冻结；强制重算须使用新的预测版本，已拒绝修改原始候选。')


def _sha(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _source(conn, issue):
    rows = conn.execute('SELECT model,front,back,created_at FROM predictions WHERE issue=? AND ticket_idx=0', (issue,)).fetchall()
    candidates = {r['model']: r for r in rows if r['model'] in MODELS}
    if len(candidates) != 9:
        raise ValueError('Portfolio requires all nine model candidates')
    return [dict(model=m, front=decode(candidates[m]['front']), back=decode(candidates[m]['back']),
                 created_at=candidates[m]['created_at']) for m in MODELS]


def _check_prospective(conn, issue, now):
    from ..tasks.dataio import next_issue_guess
    latest = conn.execute('SELECT issue,draw_date FROM draws ORDER BY issue DESC LIMIT 1').fetchone()
    if latest is None or issue != next_issue_guess(latest['issue']):
        raise ValueError('Prospective portfolio must target the next draw')
    if now >= _deadline(latest['draw_date']):
        raise ValueError('Prospective portfolio deadline has passed')


def create_portfolio(issue, kind='prospective'):
    """Freeze a same-budget snapshot; existing snapshots cannot be overwritten.

    @param kind prospective before the draw, or audited historical_simulation.
    @returns Immutable snapshot with exact uniform-draw winning coverage.
    """
    if kind not in ('prospective', 'historical_simulation'):
        raise ValueError('Invalid portfolio kind')
    if kind == 'historical_simulation' and issue not in verified_issues():
        raise ValueError('Historical simulation requires all nine verified candidates')
    with get_conn() as conn:
        source = _source(conn, issue)
        source_sha = _sha(source)
        existing = conn.execute('SELECT payload FROM portfolio_runs WHERE issue=? AND version=?', (issue, VERSION)).fetchone()
        if existing:
            saved = json.loads(existing['payload'])
            if saved['source_sha256'] != source_sha:
                raise ValueError('Original candidates changed after portfolio was frozen')
            return saved
        if kind == 'prospective':
            _check_prospective(conn, issue, _now())
        cutoff = conn.execute('SELECT MAX(issue) FROM draws WHERE issue<?', (issue,)).fetchone()[0]
    # No outcomes, financial fields or post-target model results enter the optimizer.
    numbers = [dict(model=t['model'], front=t['front'], back=t['back']) for t in source]
    result = optimize(numbers)
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if _sha(_source(conn, issue)) != source_sha:
            raise ValueError('Original candidates changed while optimizing')
        existing = conn.execute('SELECT payload FROM portfolio_runs WHERE issue=? AND version=?', (issue, VERSION)).fetchone()
        if existing:
            saved = json.loads(existing['payload'])
            if saved['source_sha256'] != source_sha:
                raise ValueError('Original candidates changed after portfolio was frozen')
            return saved
        created = _now()
        if kind == 'prospective':
            _check_prospective(conn, issue, created)
        payload = dict(issue=issue, version=VERSION, kind=kind, history_cutoff=cutoff,
                       created_at=created.isoformat(), source_sha256=source_sha,
                       original=source, cost=9 * TICKET_PRICE, **result)
        conn.execute('INSERT INTO portfolio_runs(issue,version,payload) VALUES(?,?,?)',
                     (issue, VERSION, json.dumps(payload, ensure_ascii=False)))
        conn.commit()
    return payload


def _outcome(tickets, front, back):
    hits = []
    for t in tickets:
        fh, bh = len(set(t['front']) & front), len(set(t['back']) & back)
        hits.append(dict(front_hit=fh, back_hit=bh, won=fh >= 3 or bh == 2 or (fh == 2 and bh >= 1)))
    return dict(any_win=any(t['won'] for t in hits), winning_tickets=sum(t['won'] for t in hits), tickets=hits)


def export_portfolios():
    """Settle saved snapshots from raw draw numbers; never optimize during export.

    @returns Report with simulation and prospective summaries, without estimated ROI.
    """
    runs = []
    with get_conn() as conn:
        rows = conn.execute('SELECT * FROM portfolio_runs ORDER BY issue DESC,version').fetchall()
        for row in rows:
            run = json.loads(row['payload'])
            draw = conn.execute('SELECT front,back,draw_date FROM draws WHERE issue=?', (run['issue'],)).fetchone()
            settlement = json.loads(row['settlement']) if row['settlement'] else None
            if draw and settlement is None:
                front, back = set(decode(draw['front'])), set(decode(draw['back']))
                settlement = dict(original=_outcome(run['original'], front, back),
                                  optimized=_outcome(run['tickets'], front, back),
                                  real=dict(front=sorted(front), back=sorted(back), date=draw['draw_date']),
                                  evaluated_at=datetime.now(timezone.utc).isoformat())
                conn.execute('UPDATE portfolio_runs SET settlement=? WHERE issue=? AND version=?',
                             (json.dumps(settlement), run['issue'], run['version']))
            run['result'] = settlement
            runs.append(run)
        conn.commit()
    summary = {}
    for kind in ('historical_simulation', 'prospective'):
        settled = [r for r in runs if r['kind'] == kind and r['result'] and r['version'] == VERSION]
        summary[kind] = dict(periods=len(settled), cost=len(settled) * 18,
                             first_issue=min((r['issue'] for r in settled), default=None),
                             last_issue=max((r['issue'] for r in settled), default=None),
                             original_wins=sum(r['result']['original']['any_win'] for r in settled),
                             optimized_wins=sum(r['result']['optimized']['any_win'] for r in settled))
    report = dict(version=VERSION, generated_at=datetime.now(timezone.utc).isoformat(), summary=summary, runs=runs,
                  methodology=dict(objective='at_least_one_prize', budget=18, tickets=9,
                                   assumption='uniform_independent_draws', search='three_pass_coordinate_ascent',
                                   global_optimum=False, historical_analysis='exploratory',
                                   description='只调整九模型候选的后区组合，完整计数中奖并集；理论覆盖不是盈利概率，也不证明可预测随机开奖。历史模拟与前瞻结果分开，奖金不参与目标。'))
    (EXPORT_DIR / 'portfolio.json').write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')))
    return report
