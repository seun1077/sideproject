from __future__ import annotations

import sqlite3


def review_queue(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            o.id,
            cp.brand,
            cp.name AS product,
            o.title,
            o.package_price_krw,
            o.normalized_price_krw,
            o.pack_count,
            o.volume_value,
            o.volume_unit,
            o.match_score,
            o.match_status,
            o.exclusion_reason,
            o.url
        FROM offers o
        LEFT JOIN canonical_products cp ON cp.id = o.product_id
        WHERE o.match_status IN ('candidate', 'excluded', 'rejected')
        ORDER BY
            CASE o.match_status
                WHEN 'candidate' THEN 0
                WHEN 'excluded' THEN 1
                ELSE 2
            END,
            o.match_score DESC,
            o.last_seen_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

