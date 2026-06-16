from __future__ import annotations

import traceback
from pathlib import Path

from . import __version__
from .collectors import collect_algumon_latest, collect_danawa_for_seed, collect_theqoo_deals, probe_sources
from .collectors.shared import collected_at_iso, now_stamp
from .csv_io import write_csv, write_json
from .db import apply_migrations, connect
from .evaluation import evaluate_current_deals
from .models import DealPostCandidate, OfferCandidate
from .paths import DB_PATH, PROCESSED, RAW
from .repository import (
    create_run,
    finish_run,
    record_source_check,
    upsert_default_sources,
    upsert_deal_post,
    upsert_offer,
    upsert_product,
)
from .seeds import read_seeds


def offer_to_row(offer: OfferCandidate, collected_at: str) -> dict:
    return {
        "collected_at": collected_at,
        "source": offer.source_code,
        "product_key": offer.product_key,
        "title": offer.title,
        "url": offer.url,
        "price_krw": offer.package_price_krw,
        "normalized_price_krw": offer.normalized_price_krw,
        "pack_count": offer.pack_count,
        "parsed_volume_value": offer.volume_value,
        "parsed_volume_unit": offer.volume_unit,
        "match_score": offer.match.score,
        "match_status": offer.match.status,
        "excluded_reason": offer.match.exclusion_reason,
        "usable_for_baseline": offer.match.baseline_eligible,
    }


def post_to_row(post: DealPostCandidate, collected_at: str) -> dict:
    return {
        "collected_at": collected_at,
        "source": post.source_code,
        "product_key": post.product_key,
        "title": post.title,
        "url": post.url,
        "price_krw": post.extracted_price_krw,
        "matched_keywords": post.matched_keywords,
        "match_score": post.match_score,
    }


def run_collection(
    db_path: Path = DB_PATH,
    write_csv_outputs: bool = False,
    keep_raw: bool = False,
    limit_per_seed: int = 8,
) -> dict:
    stamp = now_stamp()
    collected_at = collected_at_iso()
    seeds = read_seeds()
    raw_dir = RAW / "danawa" if keep_raw else None
    raw_algumon = RAW / f"algumon_latest_{stamp}.html" if keep_raw else None
    raw_theqoo = RAW / f"theqoo_deals_{stamp}.html" if keep_raw else None

    with connect(db_path) as conn:
        apply_migrations(conn)
        upsert_default_sources(conn)
        for seed in seeds:
            upsert_product(conn, seed)

        run_id = create_run(conn, collector_version=__version__, seed_count=len(seeds))
        source_rows: list[dict] = []
        offer_rows: list[dict] = []
        post_rows: list[dict] = []
        report_rows: list[dict] = []
        error = None
        try:
            source_rows = probe_sources(stamp=collected_at)
            for row in source_rows:
                record_source_check(conn, run_id, row)

            offers: list[OfferCandidate] = []
            for seed in seeds:
                offers.extend(
                    collect_danawa_for_seed(
                        seed,
                        limit=limit_per_seed,
                        raw_dir=raw_dir,
                        stamp=stamp,
                    )
                )

            for offer in offers:
                upsert_offer(conn, run_id, offer, collected_at)
                offer_rows.append(offer_to_row(offer, collected_at))

            algumon_posts = collect_algumon_latest(seeds, raw_path=raw_algumon)
            theqoo_posts = collect_theqoo_deals(seeds, raw_path=raw_theqoo)
            posts = [*algumon_posts, *theqoo_posts]
            for post in posts:
                upsert_deal_post(conn, post, collected_at)
                post_rows.append(post_to_row(post, collected_at))

            report_rows = evaluate_current_deals(conn, run_id)
            finish_run(
                conn,
                run_id=run_id,
                status="success",
                offer_count=len(offer_rows),
                deal_post_count=len(post_rows),
            )
        except Exception:
            error = traceback.format_exc()
            finish_run(
                conn,
                run_id=run_id,
                status="failed",
                offer_count=len(offer_rows),
                deal_post_count=len(post_rows),
                error=error,
            )
            raise

    summary = {
        "snapshot_at": stamp,
        "collected_at": collected_at,
        "db_path": str(db_path),
        "seed_count": len(seeds),
        "danawa_offer_rows": len(offer_rows),
        "algumon_deal_posts": len([row for row in post_rows if row["source"] == "algumon"]),
        "theqoo_deal_posts": len([row for row in post_rows if row["source"] == "theqoo"]),
        "source_deal_posts": len(post_rows),
        "deal_evaluations": len(report_rows),
        "top_deal_candidates": len([row for row in report_rows if (row["discount_vs_market_pct"] or 0) >= 15]),
        "csv_outputs_written": write_csv_outputs,
        "error": error,
    }
    if write_csv_outputs:
        write_csv(PROCESSED / f"source_access_{stamp}.csv", source_rows)
        write_csv(PROCESSED / f"offers_{stamp}.csv", offer_rows)
        write_csv(PROCESSED / f"deal_posts_{stamp}.csv", post_rows)
        write_csv(PROCESSED / f"deal_evaluations_{stamp}.csv", report_rows)
        write_json(PROCESSED / f"summary_{stamp}.json", summary)
    return summary
