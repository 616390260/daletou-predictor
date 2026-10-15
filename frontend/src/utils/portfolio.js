/** @returns The current pending nine-ticket snapshot, or null for stale/invalid data. */
export function currentPortfolio(report, issue) {
  return (Array.isArray(report?.runs) ? report.runs : []).find((run) =>
    run.issue === issue && run.version === report.version && run.kind === 'prospective'
    && !run.result && run.cost === 18 && run.tickets?.length === 9
    && Number.isFinite(run.total_draws) && run.total_draws > 0
    && run.original_count >= 0 && run.optimized_count >= run.original_count
    && run.optimized_count <= run.total_draws
    && run.tickets.every((t) => Array.isArray(t.front) && t.front.length === 5
      && Array.isArray(t.back) && t.back.length === 2)) || null;
}
