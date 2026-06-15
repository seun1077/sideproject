from __future__ import annotations

import sqlite3
import unittest

from beauty_deal_radar.db import apply_migrations
from beauty_deal_radar.public_api import list_deals, price_history, service_summary
from beauty_deal_radar.repository import upsert_default_sources


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)
    upsert_default_sources(conn)
    return conn


class PublicApiTest(unittest.TestCase):
    def test_empty_database_summary_is_safe(self) -> None:
        with make_conn() as conn:
            summary = service_summary(conn)

        self.assertEqual(summary["products"], 0)
        self.assertIsNone(summary["latest_run"])

    def test_deals_and_history_use_latest_successful_run(self) -> None:
        with make_conn() as conn:
            source_id = conn.execute("SELECT id FROM sources WHERE code = 'danawa'").fetchone()["id"]
            product_id = conn.execute(
                """
                INSERT INTO canonical_products (
                    canonical_key, brand, name, category, target_volume_value,
                    target_volume_unit, canonical_query
                )
                VALUES ('roundlab-birch-sun-50ml', '라운드랩', '자작나무 수분 선크림',
                        '선케어', 50, 'ml', '라운드랩 자작나무 선크림')
                RETURNING id
                """
            ).fetchone()["id"]
            run_id = conn.execute(
                """
                INSERT INTO collection_runs (
                    started_at, finished_at, collector_version, status, seed_count,
                    offer_count, deal_post_count
                )
                VALUES ('2026-06-15T00:00:00Z', '2026-06-15T00:01:00Z',
                        'test', 'success', 1, 1, 0)
                RETURNING id
                """
            ).fetchone()["id"]
            offer_id = conn.execute(
                """
                INSERT INTO offers (
                    source_id, source_offer_key, product_id, title, url,
                    package_price_krw, normalized_price_krw, pack_count,
                    match_score, match_status, baseline_eligible,
                    first_seen_at, last_seen_at
                )
                VALUES (?, 'offer-1', ?, '라운드랩 자작나무 수분 선크림 50ml',
                        'https://example.com', 12000, 12000, 1, 95,
                        'approved', 1, '2026-06-15T00:00:00Z', '2026-06-15T00:00:00Z')
                RETURNING id
                """,
                (source_id, product_id),
            ).fetchone()["id"]
            conn.execute(
                """
                INSERT INTO price_snapshots (
                    run_id, offer_id, product_id, collected_at, package_price_krw,
                    normalized_price_krw
                )
                VALUES (?, ?, ?, '2026-06-15T00:00:00Z', 12000, 12000)
                """,
                (run_id, offer_id, product_id),
            )
            conn.execute(
                """
                INSERT INTO daily_product_price_stats (
                    product_id, stat_date, min_price_krw, median_price_krw,
                    max_price_krw, offer_count, approved_offer_count
                )
                VALUES (?, date('now'), 12000, 13000, 14000, 3, 1)
                """,
                (product_id,),
            )
            conn.execute(
                """
                INSERT INTO deal_evaluations (
                    run_id, product_id, best_offer_id, evaluated_at,
                    current_min_price_krw, market_median_price_krw,
                    discount_vs_market_pct, deal_score, confidence,
                    reason, publication_status
                )
                VALUES (?, ?, ?, '2026-06-15T00:01:00Z', 12000, 15000,
                        20.0, 86, 'medium', 'test', 'auto_approved')
                """,
                (run_id, product_id, offer_id),
            )
            conn.execute(
                """
                INSERT INTO offers (
                    source_id, source_offer_key, product_id, title, url,
                    package_price_krw, normalized_price_krw, pack_count,
                    match_score, match_status, baseline_eligible,
                    first_seen_at, last_seen_at
                )
                VALUES (?, 'offer-2', ?, '라운드랩 자작나무 수분 선크림 50ml 1+1+1',
                        'https://example.com/bundle', 39000, 13000, 3, 95,
                        'approved', 1, '2026-06-15T00:00:00Z', '2026-06-15T00:00:00Z')
                """,
                (source_id, product_id),
            )

            deals = list_deals(conn, visibility="public")
            history = price_history(conn, product_id, days=90)

        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0]["brand"], "라운드랩")
        self.assertEqual(deals[0]["discount_pct"], 20.0)
        self.assertEqual(deals[0]["price_gap_krw"], 3000)
        self.assertEqual(deals[0]["other_options"][0]["unit_price_krw"], 13000)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["median_price_krw"], 13000)


if __name__ == "__main__":
    unittest.main()
