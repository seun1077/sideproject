from __future__ import annotations

import argparse
import json
from pathlib import Path

from .admin import review_queue
from .db import init_db, connect
from .evaluation import latest_deal_report
from .paths import DB_PATH
from .pipeline import run_collection
from .web_admin import run_admin_server


def _db_path(value: str | None) -> Path:
    return Path(value) if value else DB_PATH


def cmd_init_db(args: argparse.Namespace) -> None:
    applied = init_db(_db_path(args.db))
    print(json.dumps({"db_path": str(_db_path(args.db)), "applied_migrations": applied}, ensure_ascii=False, indent=2))


def cmd_collect(args: argparse.Namespace) -> None:
    summary = run_collection(
        db_path=_db_path(args.db),
        write_csv_outputs=not args.no_csv,
        keep_raw=args.keep_raw,
        limit_per_seed=args.limit_per_seed,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_report(args: argparse.Namespace) -> None:
    with connect(_db_path(args.db)) as conn:
        rows = latest_deal_report(conn, limit=args.limit)
    for row in rows:
        print(
            f"[{row['deal_score']:>3}] {row['brand']} {row['product']} "
            f"{row['current_min_price_krw']:,}원 "
            f"(median {row['market_median_price_krw']:,}원, "
            f"{row['discount_vs_market_pct']}% below, {row['confidence']})"
        )


def cmd_review_queue(args: argparse.Namespace) -> None:
    with connect(_db_path(args.db)) as conn:
        rows = review_queue(conn, limit=args.limit)
    for row in rows:
        print(
            f"#{row['id']} {row['match_status']} score={row['match_score']} "
            f"{row['brand'] or '-'} {row['product'] or '-'} | {row['title']} | "
            f"{row['normalized_price_krw'] or row['package_price_krw'] or '-'}원 | "
            f"{row['exclusion_reason'] or ''}"
        )


def cmd_admin_server(args: argparse.Namespace) -> None:
    init_db(_db_path(args.db))
    run_admin_server(host=args.host, port=args.port, db_path=_db_path(args.db))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="beauty-deal-radar")
    parser.add_argument("--db", help="SQLite DB path. Defaults to data/beauty_deals.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)

    init_db_parser = sub.add_parser("init-db", help="Create or migrate the SQLite database")
    init_db_parser.set_defaults(func=cmd_init_db)

    collect_parser = sub.add_parser("collect", help="Collect offers/deal posts and evaluate deals")
    collect_parser.add_argument("--no-csv", action="store_true", help="Do not write CSV/JSON snapshots")
    collect_parser.add_argument("--keep-raw", action="store_true", help="Persist raw HTML for parser debugging")
    collect_parser.add_argument("--limit-per-seed", type=int, default=8)
    collect_parser.set_defaults(func=cmd_collect)

    report_parser = sub.add_parser("report", help="Show latest deal evaluation report")
    report_parser.add_argument("--limit", type=int, default=20)
    report_parser.set_defaults(func=cmd_report)

    review_parser = sub.add_parser("review-queue", help="Show offers that need manual matching review")
    review_parser.add_argument("--limit", type=int, default=50)
    review_parser.set_defaults(func=cmd_review_queue)

    admin_parser = sub.add_parser("admin-server", help="Run the local admin web UI")
    admin_parser.add_argument("--host", default="127.0.0.1")
    admin_parser.add_argument("--port", type=int, default=8765)
    admin_parser.set_defaults(func=cmd_admin_server)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
