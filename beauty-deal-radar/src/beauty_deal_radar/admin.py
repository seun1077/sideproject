from __future__ import annotations

from collections.abc import Mapping
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
        WHERE o.match_status = 'candidate'
        ORDER BY
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
            "SELECT COUNT(*) FROM offers WHERE match_status = 'candidate'"
        ).fetchone()[0],
        "deal_review_queue": conn.execute(
            """
            SELECT COUNT(*)
            FROM deal_evaluations
            WHERE run_id = (SELECT MAX(id) FROM collection_runs WHERE status = 'success')
              AND publication_status IN ('auto_approved', 'needs_review')
            """
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
            o.url AS best_url,
            o.package_price_krw AS best_package_price_krw,
            o.pack_count AS best_pack_count,
            o.volume_value AS best_volume_value,
            o.volume_unit AS best_volume_unit,
            o.match_score AS best_match_score,
            o.match_status AS best_match_status,
            o.baseline_eligible AS best_baseline_eligible,
            (
                SELECT COUNT(*)
                FROM price_snapshots psx
                JOIN offers ox ON ox.id = psx.offer_id
                WHERE psx.run_id = de.run_id
                  AND psx.product_id = de.product_id
                  AND ox.baseline_eligible = 1
                  AND psx.normalized_price_krw IS NOT NULL
                  AND ox.match_status IN ('candidate', 'approved')
            ) AS offer_count,
            (
                SELECT COUNT(*)
                FROM price_snapshots psx
                JOIN offers ox ON ox.id = psx.offer_id
                WHERE psx.run_id = de.run_id
                  AND psx.product_id = de.product_id
                  AND ox.baseline_eligible = 1
                  AND psx.normalized_price_krw IS NOT NULL
                  AND ox.match_status = 'approved'
            ) AS approved_offer_count,
            (
                SELECT COUNT(*)
                FROM price_snapshots psx
                JOIN offers ox ON ox.id = psx.offer_id
                WHERE psx.run_id = de.run_id
                  AND psx.product_id = de.product_id
                  AND ox.baseline_eligible = 1
                  AND psx.normalized_price_krw IS NOT NULL
                  AND ox.match_status IN ('candidate', 'approved')
                  AND psx.normalized_price_krw <= de.current_min_price_krw * 1.15
            ) AS near_price_count,
            (
                SELECT MIN(psx.normalized_price_krw)
                FROM price_snapshots psx
                JOIN offers ox ON ox.id = psx.offer_id
                WHERE psx.run_id = de.run_id
                  AND psx.product_id = de.product_id
                  AND ox.id != de.best_offer_id
                  AND ox.baseline_eligible = 1
                  AND psx.normalized_price_krw IS NOT NULL
                  AND ox.match_status IN ('candidate', 'approved')
            ) AS second_price_krw
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


def strongest_discount(row: Mapping[str, object]) -> float | None:
    values = [row["discount_vs_30d_pct"], row["discount_vs_market_pct"]]
    numeric = [float(value) for value in values if value is not None]
    return max(numeric, default=None)


def deal_review_flags(row: Mapping[str, object]) -> list[str]:
    flags: list[str] = []
    discount = strongest_discount(row)
    current_min = int(row["current_min_price_krw"] or 0)
    second_price = row["second_price_krw"]
    offer_count = int(row["offer_count"] or 0)
    near_price_count = int(row["near_price_count"] or 0)
    best_match_score = int(row["best_match_score"] or 0)

    if row["publication_status"] not in {"auto_approved", "approved"}:
        flags.append("자동 공개 대상 아님")
    if row["best_match_status"] not in {"candidate", "approved"} or not row["best_baseline_eligible"]:
        flags.append("최저가 상품 매칭 미확정")
    if best_match_score < 90:
        flags.append("매칭 점수 낮음")
    if row["confidence"] == "low" or offer_count < 6:
        flags.append("가격 표본 부족")
    if discount is None:
        flags.append("할인 근거 부족")
    elif discount > 55:
        flags.append("할인율 과도함")
    elif discount < 25:
        flags.append("할인율 낮음")
    if second_price is None:
        flags.append("비교 가능한 2순위 가격 없음")
    elif current_min > 0 and int(second_price) > current_min * 1.35:
        flags.append("최저가만 심하게 튐")
    if near_price_count < 2:
        flags.append("근접 가격 후보 부족")
    return flags


def is_safe_auto_publish_candidate(row: Mapping[str, object]) -> bool:
    return row["publication_status"] == "auto_approved" and not deal_review_flags(row)


def auto_publish_safe_deals(conn: sqlite3.Connection, limit: int = 200) -> dict:
    rows = latest_deal_cards(conn, limit=limit)
    checked = 0
    published = 0
    skipped = 0
    for row in rows:
        if row["publication_status"] != "auto_approved":
            continue
        checked += 1
        if not is_safe_auto_publish_candidate(row):
            skipped += 1
            continue
        if row["offer_id"]:
            decide_offer(conn, int(row["offer_id"]), "approve_match", reason="safe_auto_publish")
        decide_deal(conn, int(row["evaluation_id"]), "approve_deal", reason="safe_auto_publish")
        published += 1
    return {"checked_auto_candidates": checked, "published": published, "skipped_for_review": skipped}


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
