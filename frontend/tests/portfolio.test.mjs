import test from 'node:test';
import assert from 'node:assert/strict';
import { currentPortfolio } from '../src/utils/portfolio.js';

const run = { issue: '26118', version: 'back-coverage-v1', kind: 'prospective', cost: 18,
  original_count: 9, optimized_count: 10, total_draws: 20,
  tickets: Array.from({ length: 9 }, () => ({ front: [1, 2, 3, 4, 5], back: [1, 2] })) };

test('only current, pending, same-budget prospective snapshots may be displayed as current', () => {
  assert.equal(currentPortfolio({ version: run.version, runs: [run] }, '26118'), run);
  for (const changed of [{ issue: '26117' }, { kind: 'historical_simulation' }, { result: {} },
    { cost: 20 }, { tickets: [] }, { optimized_count: 8 }]) {
    assert.equal(currentPortfolio({ version: run.version, runs: [{ ...run, ...changed }] }, '26118'), null);
  }
  assert.equal(currentPortfolio(null, '26118'), null);
});
