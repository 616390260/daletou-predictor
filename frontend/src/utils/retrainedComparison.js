/** @returns A displayable retrospective comparison, or null for unsafe/incomplete data. */
export function retrospectiveComparison(report) {
  if (report?.kind !== 'retrospective_comparison' || report.predictions_replaced !== false
    || !/^\d{5}$/.test(report.issue) || !/^\d{5}$/.test(report.trained_through_issue)
    || report.trained_through_issue >= report.issue
    || !validNumbers(report.real) || typeof report.real.date !== 'string'
    || !Array.isArray(report.models) || report.models.length !== 9) return null;

  const validModels = report.models.every((row) => typeof row?.model === 'string'
    && typeof row.label === 'string' && validTicket(row.original) && validTicket(row.retrained));
  const validSummaries = ['original', 'retrained'].every((key) => {
    const summary = report.summary?.[key];
    return summary?.tickets === report.models.length && summary.cost === summary.tickets * 2
      && Number.isInteger(summary.winning_tickets) && summary.winning_tickets >= 0
      && summary.winning_tickets <= summary.tickets
      && Number.isFinite(summary.estimated_prize) && summary.estimated_prize >= 0;
  });
  return validModels && validSummaries ? report : null;
}

/** @returns Whether front/back numbers form one legal ticket. */
function validNumbers(ticket) {
  return [[ticket?.front, 5, 35], [ticket?.back, 2, 12]].every(([numbers, length, max]) =>
    Array.isArray(numbers) && numbers.length === length && new Set(numbers).size === length
    && numbers.every((n) => Number.isInteger(n) && n >= 1 && n <= max));
}

/** @returns Whether a ticket has displayable, numeric evaluation results. */
function validTicket(ticket) {
  const result = ticket?.result;
  return validNumbers(ticket) && Number.isInteger(result?.front_hit)
    && result.front_hit >= 0 && result.front_hit <= 5
    && Number.isInteger(result.back_hit) && result.back_hit >= 0 && result.back_hit <= 2
    && Number.isFinite(result.amount) && result.amount >= 0
    && (result.level == null || typeof result.level === 'string') && typeof result.won === 'boolean';
}
