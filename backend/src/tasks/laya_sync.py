"""Idempotent Laya automation: settle saved choices, then select the next issue."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR, EXPORT_DIR
from ..db import get_conn
from ..laya.lifecycle import create_decision, inspect_sync, read_report, settle_saved

DATASET = DATA_DIR / 'laya'
REPORT = EXPORT_DIR / 'laya.json'


def active_version(report: dict) -> str:
    """@returns Validated active checkpoint name, safe for a manifest filename."""
    version = report.get('active_model', {}).get('version', '')
    if not re.fullmatch(r'daletou-[a-z0-9-]{1,60}', version):
        raise ValueError('No valid active Laya checkpoint')
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description='Synchronize independent Laya decisions')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Inspect only; emit GitHub outputs')
    mode.add_argument('--settle-only', action='store_true', help='Settle saved choices without model inference')
    args = parser.parse_args()
    with get_conn() as conn:
        settled = 0 if args.check else settle_saved(conn, REPORT)
        report = read_report(REPORT)
        status = inspect_sync(conn, report, datetime.now(timezone.utc))
        if args.settle_only:
            print(json.dumps(dict(settled=settled), ensure_ascii=False))
            return
        version = active_version(report)
        status['version'] = version
        if args.check:
            if os.environ.get('GITHUB_OUTPUT'):
                with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
                    for key, value in status.items():
                        output.write(f'{key}={str(value).lower() if isinstance(value, bool) else value}\n')
            print(json.dumps(status, ensure_ascii=False))
            return
        if status['needs_decision']:
            manifest = json.loads((DATASET / 'manifests' / f'{version}.json').read_text())
            decision = create_decision(conn, status['issue'], manifest, DATASET, REPORT)
            status['selected_model'] = decision['selected_model']
        print(json.dumps(dict(settled=settled, **status), ensure_ascii=False))


if __name__ == '__main__':
    main()
