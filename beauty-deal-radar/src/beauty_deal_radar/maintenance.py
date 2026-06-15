from __future__ import annotations

import sqlite3

from .evaluation import refresh_daily_product_price_stats
from .matching import score_offer_match
from .models import ProductSeed
from .text_utils import parse_pack_count


def recalculate_normalized_prices(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT
            o.id,
            o.title,
            o.package_price_krw,
            o.pack_count,
            o.normalized_price_krw,
            cp.target_volume_value,
            cp.target_volume_unit
        FROM offers o
        JOIN canonical_products cp ON cp.id = o.product_id
        WHERE o.package_price_krw IS NOT NULL
          AND cp.target_volume_value IS NOT NULL
          AND cp.target_volume_unit IS NOT NULL
        """
    ).fetchall()
    changed = 0
    with conn:
        for row in rows:
            target_volume = (float(row["target_volume_value"]), row["target_volume_unit"])
            pack_count = parse_pack_count(row["title"], target_volume)
            normalized_price = round(int(row["package_price_krw"]) / pack_count)
            if pack_count == row["pack_count"] and normalized_price == row["normalized_price_krw"]:
                continue
            conn.execute(
                """
                UPDATE offers
                SET pack_count = ?, normalized_price_krw = ?
                WHERE id = ?
                """,
                (pack_count, normalized_price, row["id"]),
            )
            conn.execute(
                """
                UPDATE price_snapshots
                SET normalized_price_krw = ROUND(package_price_krw / ?)
                WHERE offer_id = ?
                  AND package_price_krw IS NOT NULL
                """,
                (pack_count, row["id"]),
            )
            changed += 1

        stat_dates = [
            row["stat_date"]
            for row in conn.execute(
                """
                SELECT DISTINCT substr(collected_at, 1, 10) AS stat_date
                FROM price_snapshots
                WHERE collected_at IS NOT NULL
                ORDER BY stat_date ASC
                """
            ).fetchall()
        ]
        for stat_date in stat_dates:
            refresh_daily_product_price_stats(conn, stat_date)

    return {
        "checked_offers": len(rows),
        "updated_offers": changed,
        "refreshed_stat_dates": len(stat_dates),
    }


def recalculate_candidate_matches(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT
            o.id,
            o.title,
            o.match_status,
            o.match_score,
            o.exclusion_reason,
            o.baseline_eligible,
            cp.brand,
            cp.name,
            cp.category,
            cp.canonical_query,
            cp.target_volume_value,
            cp.target_volume_unit
        FROM offers o
        JOIN canonical_products cp ON cp.id = o.product_id
        WHERE o.match_status IN ('candidate', 'excluded', 'rejected')
        """
    ).fetchall()
    changed = 0
    with conn:
        for row in rows:
            volume_hint = (
                f"{float(row['target_volume_value']):g}{row['target_volume_unit']}"
                if row["target_volume_value"] and row["target_volume_unit"]
                else ""
            )
            seed = ProductSeed(
                brand=row["brand"],
                product=row["name"],
                query=row["canonical_query"],
                category=row["category"],
                volume_hint=volume_hint,
            )
            match = score_offer_match(seed, row["title"])
            if (
                match.status == row["match_status"]
                and match.score == row["match_score"]
                and match.exclusion_reason == (row["exclusion_reason"] or "")
                and int(match.baseline_eligible) == int(row["baseline_eligible"])
            ):
                continue
            conn.execute(
                """
                UPDATE offers
                SET match_score = ?,
                    match_status = ?,
                    exclusion_reason = ?,
                    baseline_eligible = ?
                WHERE id = ?
                """,
                (
                    match.score,
                    match.status,
                    match.exclusion_reason or None,
                    1 if match.baseline_eligible else 0,
                    row["id"],
                ),
            )
            changed += 1
    return {"checked_offers": len(rows), "updated_offers": changed}
