/** @returns Chronological pre-target draws; target and future draws are excluded. */
export function trendHistory(history, issue, limit = 30) {
  return history.filter((draw) => String(draw.issue) < String(issue))
    .slice().sort((a, b) => String(a.issue).localeCompare(String(b.issue))).slice(-limit);
}

/** @returns Separate front/back candidate rows with observed presence and bounded omissions. */
export function trendRows(draws, decision) {
  return ["front", "back"].flatMap((zone) => (decision[zone] || []).map((number) => {
    const present = draws.map((draw) => (draw[zone] || []).includes(number));
    const lastSeen = present.lastIndexOf(true);
    return { zone, number, present, count: present.filter(Boolean).length,
      omission: lastSeen < 0 ? `≥${draws.length}` : String(draws.length - lastSeen - 1) };
  }));
}
