"""Repair source money fields only after full historical identity validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR, DB_PATH, MONEY_FEATURE_VERSION
from ..scraper.fetch_history import FIVEHUNDRED_URL, _fetch_500, _parse_500_html


def repair_financials(conn, records: list[dict], *, apply: bool = True) -> dict:
    """Validate all DB draws against canonical records, then update money only.

    @param conn SQLite connection, with no pending changes from other tasks.
    @param records Complete parsed 500 history; no fallback source is accepted.
    @param apply Whether to write changes, otherwise report a dry run.
    @returns Counts, changed issue range and skipped empty source issues.
    """
    if not records:
        raise ValueError("Empty canonical history")
    source = {}
    for record in records:
        issue = record["issue"]
        if issue in source:
            raise ValueError(f"Duplicate canonical issue: {issue}")
        source[issue] = record

    changes = []
    skipped = []
    rows = conn.execute("SELECT issue, draw_date, front, back, sales, pool FROM draws ORDER BY issue").fetchall()
    for row in rows:
        issue, draw_date, front, back, sales, pool = tuple(row)
        canonical = source.get(issue)
        if canonical is None:
            raise ValueError(f"Missing canonical issue: {issue}")
        if (draw_date, front, back) != tuple(canonical[key] for key in ("draw_date", "front", "back")):
            raise ValueError(f"Draw identity mismatch: {issue}")
        new_sales, new_pool = canonical["sales"], canonical["pool"]
        if new_sales <= 0 or new_pool <= 0:
            skipped.append(issue)
            continue
        if (sales, pool) != (new_sales, new_pool):
            changes.append((new_sales, new_pool, issue))

    if apply:
        with conn:
            conn.executemany("UPDATE draws SET sales = ?, pool = ? WHERE issue = ?", changes)
    issues = [change[2] for change in changes]
    return {
        "applied": apply,
        "canonical_count": len(records),
        "validated_count": len(rows),
        "updated_count": len(changes) if apply else 0,
        "would_update_count": len(changes),
        "issue_start": min(issues) if issues else None,
        "issue_end": max(issues) if issues else None,
        "skipped_empty_source": skipped,
        "money_feature_version": MONEY_FEATURE_VERSION,
    }


def run(db_path: Path = DB_PATH, audit_path: Path = DATA_DIR / "financial_repair.json", *, apply: bool = False) -> dict:
    """Fetch canonical history once and persist a reproducible repair audit.

    @param db_path Existing database to validate and optionally repair.
    @param audit_path JSON audit destination.
    @param apply Whether to apply the financial updates.
    @returns Audit including SHA-256 of the decoded source HTML encoded as UTF-8.
    """
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    html = _fetch_500(start="07001", end="99999")
    records = _parse_500_html(html)
    mode = "rw" if apply else "ro"
    conn = sqlite3.connect(db_path.as_uri() + f"?mode={mode}", uri=True)
    try:
        result = repair_financials(conn, records, apply=apply)
    finally:
        conn.close()
    audit = {
        "source": FIVEHUNDRED_URL.format(start="07001", end="99999"),
        "source_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "source_hash_encoding": "decoded HTML re-encoded as UTF-8",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": str(db_path),
        **result,
    }
    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="严格核对历史身份后仅修复销量和奖池，默认预览")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--audit", type=Path, default=DATA_DIR / "financial_repair.json")
    parser.add_argument("--apply", action="store_true", help="写入金额修复；不传则仅预览")
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.audit, apply=args.apply), ensure_ascii=False, indent=2))
