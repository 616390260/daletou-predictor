"""Immutable prospective choices and model-free settlement for Laya."""
from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

from ..config import MODELS, MODEL_LABELS
from ..utils.draw_calendar import next_draw_deadline
from ..utils.numbers import count_hits, decode
from ..utils.prizes import previous_pool, prize_for_hits
from .dataset import _issue, _ticket, build_state
from .experiment import local_model_lock, resolve_checkpoint, write_report
from .runtime import LayaScorer, choose_candidate, validate_model_cutoff


def _now():
    return datetime.now(timezone.utc)


def read_report(path: Path) -> dict:
    """@returns Existing report, refusing ambiguous duplicate decision issues."""
    report = json.loads(path.read_text()) if path.exists() else {}
    issues = [_issue(d['issue']) for d in report.get('decisions', [])]
    if len(issues) != len(set(issues)):
        raise ValueError('Duplicate Laya decision issues')
    return report


def _candidates(conn, issue):
    rows = conn.execute(
        'SELECT model,front,back,created_at FROM predictions WHERE issue=? AND ticket_idx=0', (issue,)
    ).fetchall()
    candidates = {r['model']: dict(r) for r in rows}
    if len(rows) != len(MODELS) or set(candidates) != set(MODELS):
        return []
    return [candidates[model] for model in MODELS]


def inspect_sync(conn, report: dict, now: datetime) -> dict:
    """Inspect the next issue without loading a model or changing any data.

    @returns Issue, needs_decision flag and an explicit skip reason.
    """
    latest = conn.execute('SELECT issue,draw_date FROM draws ORDER BY issue DESC LIMIT 1').fetchone()
    if latest is None:
        return dict(issue='', needs_decision=False, reason='no_history')
    issue = f'{int(latest["issue"]) + 1:05d}'
    _issue(issue)
    if any(d['issue'] == issue for d in report.get('decisions', [])):
        return dict(issue=issue, needs_decision=False, reason='already_selected')
    if now >= next_draw_deadline(latest['draw_date']):
        return dict(issue=issue, needs_decision=False, reason='deadline_passed')
    if not _candidates(conn, issue):
        return dict(issue=issue, needs_decision=False, reason='missing_candidates')
    return dict(issue=issue, needs_decision=True, reason='ready')


def _require_prospective(conn, issue, report, now):
    status = inspect_sync(conn, report, now)
    if status['issue'] != issue:
        raise ValueError(f'Only the next undrawn issue may be selected: {status["issue"]}')
    if not status['needs_decision']:
        raise ValueError(f'Laya selection refused: {status["reason"]}')
    return status


def _source(conn, issue, verified_start):
    latest = conn.execute('SELECT draw_date FROM draws ORDER BY issue DESC LIMIT 1').fetchone()
    deadline = next_draw_deadline(latest['draw_date'])
    rows = _candidates(conn, issue)
    if not rows:
        raise ValueError('Laya requires all nine candidates')
    source = []
    for row in rows:
        created = datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        if created >= deadline:
            raise ValueError('Candidate was created after the prospective deadline')
        front, back = _ticket(decode(row['front']), decode(row['back']))
        source.append({**row, 'front': front, 'back': back,
                       'state': build_state(conn, issue, row['model'], front, back, verified_start)})
    return source


def _sha(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def create_decision(conn, issue: str, manifest: dict, dataset: Path, report_path: Path,
                    scorer_factory=None) -> dict:
    """Freeze one next-issue choice; existing choices are never rescored or replaced.

    @param scorer_factory Optional lazy scorer factory for an alternate inference runtime.
    @returns The immutable saved choice, including its model version and input digest.
    """
    _issue(issue)
    report = read_report(report_path)
    existing = next((d for d in report.get('decisions', []) if d['issue'] == issue), None)
    if existing is not None:
        return existing
    _require_prospective(conn, issue, report, _now())
    validate_model_cutoff(manifest['trained_through_issue'], issue)
    meta = json.loads((dataset / 'metadata.json').read_text())
    source = _source(conn, issue, meta['verified_start_issue'])
    source_sha = _sha(source)
    with local_model_lock() if scorer_factory is None else nullcontext():
        scorer = (scorer_factory() if scorer_factory else
                  LayaScorer(resolve_checkpoint(dataset, manifest), manifest['trained_through_issue']))
        ranked = [{**row, 'score': scorer.score(row['state'], issue)} for row in source]
    chosen = choose_candidate(ranked)
    report = read_report(report_path)
    existing = next((d for d in report.get('decisions', []) if d['issue'] == issue), None)
    if existing is not None:
        return existing
    created = _now()
    _require_prospective(conn, issue, report, created)
    if _sha(_source(conn, issue, meta['verified_start_issue'])) != source_sha:
        raise ValueError('Laya candidate inputs changed during scoring')
    decision = dict(
        issue=issue, selected_model=chosen['model'], label=MODEL_LABELS[chosen['model']],
        front=chosen['front'], back=chosen['back'], score=round(chosen['score'], 6),
        model_version=manifest['version'], trained_through_issue=manifest['trained_through_issue'],
        candidate_scores=[dict(model=r['model'], score=round(r['score'], 6)) for r in ranked],
        kind='prospective', result=None, decided_at=created.isoformat(), source_sha256=source_sha,
    )
    decisions = [*report.get('decisions', []), decision]
    decisions.sort(key=lambda d: d['issue'], reverse=True)
    write_report(report_path, {'decisions': decisions})
    return decision


def settle_saved(conn, report_path: Path) -> int:
    """Append real results to saved choices without rescoring or changing their identity.

    @returns Count of newly settled decisions; no write occurs when nothing changed.
    """
    report = read_report(report_path)
    changed = 0
    for decision in report.get('decisions', []):
        if decision.get('result') is not None:
            continue
        draw = conn.execute('SELECT draw_date,front,back FROM draws WHERE issue=?', (decision['issue'],)).fetchone()
        if draw is None:
            continue
        front, back = _ticket(decision['front'], decision['back'])
        fh, bh = count_hits(front, back, decode(draw['front']), decode(draw['back']))
        level, amount = prize_for_hits(decision['issue'], fh, bh, previous_pool(conn, decision['issue']))
        decision['result'] = dict(front_hit=fh, back_hit=bh, level=level, amount=amount,
                                  amount_basis='estimated_rule_schedule')
        decision['real'] = dict(front=decode(draw['front']), back=decode(draw['back']), date=draw['draw_date'])
        decision['evaluated_at'] = _now().isoformat()
        changed += 1
    if changed:
        write_report(report_path, {'decisions': report['decisions']})
    return changed
