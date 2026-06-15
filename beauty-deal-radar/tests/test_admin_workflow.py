from __future__ import annotations

import sqlite3
import unittest

from beauty_deal_radar.admin import (
    auto_publish_safe_deals,
    deal_review_flags,
    decide_source_deal,
    latest_deal_cards,
    review_queue,
    source_deal_queue,
)
from beauty_deal_radar.db import apply_migrations
from beauty_deal_radar.repository import upsert_default_sources


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)
    upsert_default_sources(conn)
    return conn


def seed_deal(conn: sqlite3.Connection, *, prices: list[int], discount_pct: float = 33.3) -> int:
    source_id = conn.execute("SELECT id FROM sources WHERE code = 'danawa'").fetchone()["id"]
    product_id = conn.execute(
        """
        INSERT INTO canonical_products (
            canonical_key, brand, name, category, target_volume_value,
            target_volume_unit, canonical_query
        )
        VALUES ('test-sun-cream', '테스트', '선크림', '선케어', 50, 'ml', '테스트 선크림')
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
                'test', 'success', 1, ?, 0)
        RETURNING id
        """,
        (len(prices),),
    ).fetchone()["id"]
    offer_ids = []
    for index, price in enumerate(prices):
        offer_id = conn.execute(
            """
            INSERT INTO offers (
                source_id, source_offer_key, product_id, title, url,
                package_price_krw, normalized_price_krw, pack_count,
                match_score, match_status, baseline_eligible,
                first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, '테스트 선크림 50ml', 'https://example.com',
                    ?, ?, 1, 95, 'candidate', 1,
                    '2026-06-15T00:00:00Z', '2026-06-15T00:00:00Z')
            RETURNING id
            """,
            (source_id, f"offer-{index}", product_id, price, price),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO price_snapshots (
                run_id, offer_id, product_id, collected_at, package_price_krw,
                normalized_price_krw
            )
            VALUES (?, ?, ?, '2026-06-15T00:00:00Z', ?, ?)
            """,
            (run_id, offer_id, product_id, price, price),
        )
        offer_ids.append(offer_id)
    best_price = min(prices)
    evaluation_id = conn.execute(
        """
        INSERT INTO deal_evaluations (
            run_id, product_id, best_offer_id, evaluated_at,
            current_min_price_krw, market_median_price_krw,
            discount_vs_market_pct, deal_score, confidence,
            reason, publication_status
        )
        VALUES (?, ?, ?, '2026-06-15T00:01:00Z', ?, 15000,
                ?, 100, 'medium', 'test', 'auto_approved')
        RETURNING id
        """,
        (run_id, product_id, offer_ids[prices.index(best_price)], best_price, discount_pct),
    ).fetchone()["id"]
    return evaluation_id


class AdminWorkflowTest(unittest.TestCase):
    def test_auto_publish_safe_deals_approves_only_low_risk_candidates(self) -> None:
        with make_conn() as conn:
            seed_deal(conn, prices=[10000, 11000, 11200, 13000, 14000, 16000])

            result = auto_publish_safe_deals(conn)
            published = conn.execute("SELECT COUNT(*) FROM published_deals").fetchone()[0]

        self.assertEqual(result["published"], 1)
        self.assertEqual(published, 1)

    def test_auto_publish_keeps_extreme_outliers_for_review(self) -> None:
        with make_conn() as conn:
            seed_deal(conn, prices=[5000, 12000, 13000, 14000, 15000, 16000], discount_pct=66.7)

            result = auto_publish_safe_deals(conn)
            rows = latest_deal_cards(conn)
            flags = deal_review_flags(rows[0])
            published = conn.execute("SELECT COUNT(*) FROM published_deals").fetchone()[0]

        self.assertEqual(result["published"], 0)
        self.assertEqual(published, 0)
        self.assertIn("할인율 과도함", flags)

    def test_match_review_queue_only_shows_pending_candidates(self) -> None:
        with make_conn() as conn:
            seed_deal(conn, prices=[10000, 11000, 11200, 13000, 14000, 16000])
            first_offer = conn.execute("SELECT id FROM offers ORDER BY id LIMIT 1").fetchone()["id"]
            second_offer = conn.execute("SELECT id FROM offers ORDER BY id LIMIT 1 OFFSET 1").fetchone()["id"]
            conn.execute("UPDATE offers SET match_status = 'excluded' WHERE id = ?", (first_offer,))
            conn.execute("UPDATE offers SET match_status = 'rejected' WHERE id = ?", (second_offer,))

            rows = review_queue(conn, limit=10)

        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["match_status"] == "candidate" for row in rows))

    def test_source_deal_queue_and_decision_workflow(self) -> None:
        with make_conn() as conn:
            product_id = conn.execute(
                """
                INSERT INTO canonical_products (
                    canonical_key, brand, name, category, target_volume_value,
                    target_volume_unit, canonical_query
                )
                VALUES ('test-cream', '테스트', '크림', '크림', 50, 'ml', '테스트 크림')
                RETURNING id
                """
            ).fetchone()["id"]
            source_id = conn.execute("SELECT id FROM sources WHERE code = 'algumon'").fetchone()["id"]
            deal_post_id = conn.execute(
                """
                INSERT INTO deal_posts (
                    source_id, source_post_key, product_id, title, url, collected_at,
                    extracted_price_krw, matched_keywords, match_score
                )
                VALUES (?, 'post-1', ?, '테스트 크림 특가 9900원', 'https://example.com/deal',
                        '2026-06-15T00:00:00Z', 9900, '테스트,크림', 80)
                RETURNING id
                """,
                (source_id, product_id),
            ).fetchone()["id"]

            rows = source_deal_queue(conn, limit=10)
            decide_source_deal(conn, deal_post_id, "approve_source_deal")
            reviewed = conn.execute("SELECT COUNT(*) FROM source_deal_reviews").fetchone()[0]
            status = conn.execute("SELECT match_status FROM deal_posts WHERE id = ?", (deal_post_id,)).fetchone()[0]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "테스트 크림 특가 9900원")
        self.assertEqual(status, "approved")
        self.assertEqual(reviewed, 1)


if __name__ == "__main__":
    unittest.main()
