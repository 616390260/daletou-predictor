import test from 'node:test';
import assert from 'node:assert/strict';
import { retrospectiveComparison } from '../src/utils/retrainedComparison.js';

const ticket = {
  front: [1, 2, 3, 4, 5], back: [1, 2],
  result: { front_hit: 0, back_hit: 0, level: null, amount: 0, won: false },
};
const summary = { tickets: 9, cost: 18, winning_tickets: 0, estimated_prize: 0 };
const report = {
  issue: '26118', kind: 'retrospective_comparison', trained_through_issue: '26117',
  predictions_replaced: false,
  real: { date: '2026-10-17', front: [2, 9, 21, 26, 32], back: [6, 12] },
  models: Array.from({ length: 9 }, (_, i) => ({
    model: `model-${i}`, label: `Model ${i}`, original: ticket, retrained: ticket,
  })),
  summary: { original: summary, retrained: summary },
};

test('accepts an isolated retrospective comparison without replacing original records', () => {
  assert.equal(retrospectiveComparison(report), report);
});

test('rejects missing data and reports that could be confused with prospective records', () => {
  for (const data of [null, [], {}, { ...report, kind: 'prospective' },
    { ...report, predictions_replaced: true }, { ...report, predictions_replaced: undefined },
    { ...report, trained_through_issue: '26118' }]) {
    assert.equal(retrospectiveComparison(data), null);
  }
});

test('rejects incomplete tickets, results and summaries before the view renders them', () => {
  for (const change of [
    { real: null }, { models: [] },
    { models: report.models.map((row) => ({ ...row, retrained: { ...ticket, front: [1] } })) },
    { models: report.models.map((row) => ({ ...row, original: { ...ticket, result: null } })) },
    { summary: { original: summary, retrained: { ...summary, estimated_prize: '5' } } },
  ]) {
    assert.equal(retrospectiveComparison({ ...report, ...change }), null);
  }
});
