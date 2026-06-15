from __future__ import annotations

import sqlite3

from .repository import utc_now


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


def dashboard_metrics(conn: sqlite3.Connection) -> dict:
    latest_run = conn.execute(
        """
        SELECT id, started_at, finished_at, status, seed_count, offer_count, deal_post_count, error
        FROM collection_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    metrics = {
        "latest_run": dict(latest_run) if latest_run else None,
        "products": conn.execute("SELECT COUNT(*) FROM canonical_products").fetchone()[0],
        "offers": conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0],
        "price_snapshots": conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0],
        "review_queue": conn.execute(
            "SELECT COUNT(*) FROM offers WHERE match_status IN ('candidate', 'excluded', 'rejected')"
        ).fetchone()[0],
        "auto_approved_deals": conn.execute(
            "SELECT COUNT(*) FROM deal_evaluations WHERE publication_status = 'auto_approved'"
        ).fetchone()[0],
        "needs_review_deals": conn.execute(
            "SELECT COUNT(*) FROM deal_evaluations WHERE publication_status = 'needs_review'"
        ).fetchone()[0],
    }
    return metrics


def latest_deal_cards(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            de.id AS evaluation_id,
            de.evaluated_at,
            de.publication_status,
            cp.brand,
            cp.name AS product,
            cp.category,
            de.current_min_price_krw,
            de.market_median_price_krw,
            de.historical_median_30d_krw,
            de.historical_median_90d_krw,
            de.discount_vs_market_pct,
            de.discount_vs_30d_pct,
            de.discount_vs_90d_pct,
            de.deal_score,
            de.confidence,
            o.id AS offer_id,
            o.title AS best_title,
            o.url AS best_url
        FROM deal_evaluations de
        JOIN canonical_products cp ON cp.id = de.product_id
        LEFT JOIN offers o ON o.id = de.best_offer_id
        WHERE de.run_id = (SELECT MAX(id) FROM collection_runs WHERE status = 'success')
        ORDER BY
            CASE de.publication_status
                WHEN 'auto_approved' THEN 0
                WHEN 'needs_review' THEN 1
                WHEN 'approved' THEN 2
                ELSE 3
            END,
            de.deal_score DESC,
            de.discount_vs_market_pct DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def decide_offer(conn: sqlite3.Connection, offer_id: int, decision: str, reason: str | None = None) -> None:
    mapping = {
        "approve_match": ("approved", 1),
        "reject_match": ("rejected", 0),
        "exclude": ("excluded", 0),
    }
    if decision not in mapping:
        raise ValueError(f"Unsupported offer decision: {decision}")
    status, eligible = mapping[decision]
    with conn:
        conn.execute(
            """
            UPDATE offers
            SET match_status = ?, baseline_eligible = ?, exclusion_reason = ?
            WHERE id = ?
            """,
            (status, eligible, reason, offer_id),
        )
        conn.execute(
            """
            INSERT INTO review_decisions (target_type, target_id, decision, reason, decided_at)
            VALUES ('offer', ?, ?, ?, ?)
            """,
            (offer_id, decision, reason, utc_now()),
        )


def decide_deal(conn: sqlite3.Connection, evaluation_id: int, decision: str, reason: str | None = None) -> None:
    status_by_decision = {
        "approve_deal": "approved",
        "reject_deal": "rejected",
        "hold": "needs_review",
    }
    if decision not in status_by_decision:
        raise ValueError(f"Unsupported deal decision: {decision}")
    status = status_by_decision[decision]
    with conn:
        conn.execute(
            """
            UPDATE deal_evaluations
            SET publication_status = ?, publication_note = ?
            WHERE id = ?
            """,
            (status, reason, evaluation_id),
        )
        conn.execute(
            """
            INSERT INTO review_decisions (target_type, target_id, decision, reason, decided_at)
            VALUES ('deal_evaluation', ?, ?, ?, ?)
            """,
            (evaluation_id, decision, reason, utc_now()),
        )
        if decision == "approve_deal":
            row = conn.execute(
                """
                SELECT
                    de.id AS evaluation_id,
                    de.product_id,
                    de.best_offer_id,
                    de.current_min_price_krw,
                    de.discount_vs_market_pct,
                    de.discount_vs_30d_pct,
                    de.deal_score,
                    cp.brand,
                    cp.name AS product
                FROM deal_evaluations de
                JOIN canonical_products cp ON cp.id = de.product_id
                WHERE de.id = ?
                """,
                (evaluation_id,),
            ).fetchone()
            if row:
                discount = row["discount_vs_30d_pct"]
                if discount is None:
                    discount = row["discount_vs_market_pct"]
                conn.execute(
                    """
                    INSERT INTO published_deals (
                        deal_evaluation_id, product_id, offer_id, title, current_price_krw,
                        discount_pct, deal_score, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'published')
                    ON CONFLICT(deal_evaluation_id) DO UPDATE SET
                        current_price_krw=excluded.current_price_krw,
                        discount_pct=excluded.discount_pct,
                        deal_score=excluded.deal_score,
                        status='published',
                        expired_at=NULL
                    """,
                    (
                        row["evaluation_id"],
                        row["product_id"],
                        row["best_offer_id"],
                        f"{row['brand']} {row['product']}",
                        row["current_min_price_krw"],
                        discount,
                        row["deal_score"],
                    ),
                )
