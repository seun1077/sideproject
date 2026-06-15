from __future__ import annotations

import sqlite3
import unittest

from beauty_deal_radar.db import apply_migrations
from beauty_deal_radar.evaluation import evaluate_current_deals
from beauty_deal_radar.repository import upsert_default_sources


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)
    upsert_default_sources(conn)
    return conn


class EvaluationTest(unittest.TestCase):
    def test_current_evaluation_ignores_stale_offer_without_run_snapshot(self) -> None:
        with make_conn() as conn:
            source_id = conn.execute("SELECT id FROM sources WHERE code = 'danawa'").fetchone()["id"]
            product_id = conn.execute(
                """
                INSERT INTO canonical_products (
                    canonical_key, brand, name, category, target_volume_value,
                    target_volume_unit, canonical_query
                )
                VALUES ('mediheal-pad', '메디힐', '마데카소사이드 흔적 패드',
                        '패드', 100, '매', '메디힐 마데카소사이드 흔적 패드')
                RETURNING id
                """
            ).fetchone()["id"]
            old_run_id = conn.execute(
                """
                INSERT INTO collection_runs (
                    started_at, finished_at, collector_version, status, seed_count,
                    offer_count, deal_post_count
                )
                VALUES ('2026-06-15T08:00:00Z', '2026-06-15T08:01:00Z',
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
                VALUES (?, 'stale-offer', ?, '메디힐 마데카소사이드 흔적 패드 100매',
                        'https://example.com/stale', 21930, 21930, 1, 95,
                        'candidate', 1, '2026-06-15T08:00:00Z', '2026-06-15T08:00:00Z')
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
                VALUES (?, ?, ?, '2026-06-15T08:00:00Z', 21930, 21930)
                """,
                (old_run_id, offer_id, product_id),
            )
            new_run_id = conn.execute(
                """
                INSERT INTO collection_runs (
                    started_at, finished_at, collector_version, status, seed_count,
                    offer_count, deal_post_count
                )
                VALUES ('2026-06-15T10:00:00Z', '2026-06-15T10:01:00Z',
                        'test', 'success', 1, 0, 0)
                RETURNING id
                """
            ).fetchone()["id"]

            rows = evaluate_current_deals(conn, new_run_id)
            evaluation_count = conn.execute("SELECT COUNT(*) FROM deal_evaluations").fetchone()[0]

        self.assertEqual(rows, [])
        self.assertEqual(evaluation_count, 0)


if __name__ == "__main__":
    unittest.main()
