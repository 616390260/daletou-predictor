"""Create fixed-budget portfolios without changing any original prediction."""
import argparse

from ..db import init_db
from ..portfolio.service import create_portfolio, export_portfolios, verified_issues


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='生成独立九注覆盖方案')
    parser.add_argument('--issue')
    parser.add_argument('--backtest', action='store_true')
    args = parser.parse_args()
    init_db()
    if args.backtest:
        for issue in sorted(verified_issues()):
            run = create_portfolio(issue, kind='historical_simulation')
            print(f"{issue}: {run['original_count']/run['total_draws']:.4%} → {run['optimized_count']/run['total_draws']:.4%}", flush=True)
    if args.issue:
        run = create_portfolio(args.issue)
        print(f"{args.issue}: {run['original_count']/run['total_draws']:.4%} → {run['optimized_count']/run['total_draws']:.4%}")
    export_portfolios()
