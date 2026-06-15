from __future__ import annotations

import math
import sqlite3
import statistics

from .repository import utc_now


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    return int(statistics.median(values))


def refresh_daily_product_price_stats(conn: sqlite3.Connection, stat_date: str) -> None:
    products = conn.execute("SELECT id FROM canonical_products WHERE status = 'active'").fetchall()
    with conn:
        for product in products:
            rows = conn.execute(
                """
                SELECT ps.normalized_price_krw, o.match_status
                FROM price_snapshots ps
                JOIN offers o ON o.id = ps.offer_id
                WHERE ps.product_id = ?
                  AND substr(ps.collected_at, 1, 10) = ?
                  AND ps.normalized_price_krw IS NOT NULL
                  AND o.baseline_eligible = 1
                  AND o.match_status IN ('candidate', 'approved')
                """,
                (product["id"], stat_date),
            ).fetchall()
            prices = sorted(int(row["normalized_price_krw"]) for row in rows)
            if not prices:
                continue
            approved_count = len([row for row in rows if row["match_status"] == "approved"])
            conn.execute(
                """
                INSERT INTO daily_product_price_stats (
                    product_id, stat_date, source_scope, min_price_krw, median_price_krw,
                    max_price_krw, offer_count, approved_offer_count
                )
                VALUES (?, ?, 'all', ?, ?, ?, ?, ?)
                ON CONFLICT(product_id, stat_date, source_scope) DO UPDATE SET
                    min_price_krw=excluded.min_price_krw,
                    median_price_krw=excluded.median_price_krw,
                    max_price_krw=excluded.max_price_krw,
                    offer_count=excluded.offer_count,
                    approved_offer_count=excluded.approved_offer_count,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (
                    product["id"],
                    stat_date,
                    prices[0],
                    int(statistics.median(prices)),
                    prices[-1],
                    len(prices),
                    approved_count,
                ),
            )


def historical_median(conn: sqlite3.Connection, product_id: int, days: int, current_date: str) -> int | None:
    rows = conn.execute(
        """
        SELECT median_price_krw
        FROM daily_product_price_stats
        WHERE product_id = ?
          AND stat_date < ?
          AND stat_date >= date(?, ?)
          AND median_price_krw IS NOT NULL
        ORDER BY stat_date DESC
        """,
        (product_id, current_date, current_date, f"-{days} day"),
    ).fetchall()
    return _median([int(row["median_price_krw"]) for row in rows])


def publication_status_for(
    discount_vs_market: float | None,
    discount_vs_30d: float | None,
    offer_count: int,
    confidence: str,
) -> str:
    strongest_discount = max(
        [value for value in [discount_vs_30d, discount_vs_market] if value is not None],
        default=None,
    )
    if strongest_discount is None:
        return "draft"
    if offer_count >= 5 and confidence in {"medium", "high"} and 25 <= strongest_discount <= 55:
        return "auto_approved"
    if strongest_discount >= 15:
        return "needs_review"
    return "draft"


def evaluate_current_deals(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    products = conn.execute(
        "SELECT id, brand, name, category, target_volume_value, target_volume_unit FROM canonical_products WHERE status = 'active'"
    ).fetchall()
    evaluated_at = utc_now()
    current_date = evaluated_at[:10]
    refresh_daily_product_price_stats(conn, current_date)
    rows: list[dict] = []
    with conn:
        for product in products:
            offers = conn.execute(
                """
                SELECT id, title, url, package_price_krw, normalized_price_krw
                FROM offers
                WHERE product_id = ?
                  AND baseline_eligible = 1
                  AND normalized_price_krw IS NOT NULL
                  AND match_status IN ('candidate', 'approved')
                ORDER BY normalized_price_krw ASC
                """,
                (product["id"],),
            ).fetchall()
            if not offers:
                continue
            prices = sorted(int(offer["normalized_price_krw"]) for offer in offers)
            current_min = prices[0]
            market_median = int(statistics.median(prices))
            discount_vs_market = (
                round((market_median - current_min) / market_median * 100, 1)
                if market_median
                else None
            )
            median_30d = historical_median(conn, int(product["id"]), 30, current_date)
            median_90d = historical_median(conn, int(product["id"]), 90, current_date)
            discount_vs_30d = (
                round((median_30d - current_min) / median_30d * 100, 1)
                if median_30d
                else None
            )
            discount_vs_90d = (
                round((median_90d - current_min) / median_90d * 100, 1)
                if median_90d
                else None
            )
            score = 50
            primary_discount = discount_vs_30d if discount_vs_30d is not None else discount_vs_market
            if primary_discount is not None:
                score = max(0, min(100, 50 + math.floor(primary_discount * 1.8)))
            confidence = "low"
            if len(prices) >= 6:
                confidence = "medium"
            if len(prices) >= 10:
                confidence = "high"
            best = offers[0]
            status = publication_status_for(discount_vs_market, discount_vs_30d, len(prices), confidence)
            reason = "historical_30d" if median_30d else "current_market_median_bootstrap"
            conn.execute(
                """
                INSERT INTO deal_evaluations (
                    run_id, product_id, best_offer_id, evaluated_at, current_min_price_krw,
                    market_median_price_krw, historical_median_30d_krw, historical_median_90d_krw,
                    discount_vs_market_pct, discount_vs_30d_pct, discount_vs_90d_pct,
                    deal_score, confidence, reason, publication_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, product_id) DO UPDATE SET
                    best_offer_id=excluded.best_offer_id,
                    evaluated_at=excluded.evaluated_at,
                    current_min_price_krw=excluded.current_min_price_krw,
                    market_median_price_krw=excluded.market_median_price_krw,
                    historical_median_30d_krw=excluded.historical_median_30d_krw,
                    historical_median_90d_krw=excluded.historical_median_90d_krw,
                    discount_vs_market_pct=excluded.discount_vs_market_pct,
                    discount_vs_30d_pct=excluded.discount_vs_30d_pct,
                    discount_vs_90d_pct=excluded.discount_vs_90d_pct,
                    deal_score=excluded.deal_score,
                    confidence=excluded.confidence,
                    reason=excluded.reason,
                    publication_status=excluded.publication_status
                """,
                (
                    run_id,
                    product["id"],
                    best["id"],
                    evaluated_at,
                    current_min,
                    market_median,
                    median_30d,
                    median_90d,
                    discount_vs_market,
                    discount_vs_30d,
                    discount_vs_90d,
                    score,
                    confidence,
                    reason,
                    status,
                ),
            )
            rows.append(
                {
                    "product_id": product["id"],
                    "brand": product["brand"],
                    "product": product["name"],
                    "category": product["category"],
                    "current_min_price_krw": current_min,
                    "market_median_price_krw": market_median,
                    "historical_median_30d_krw": median_30d,
                    "historical_median_90d_krw": median_90d,
                    "discount_vs_market_pct": discount_vs_market,
                    "discount_vs_30d_pct": discount_vs_30d,
                    "discount_vs_90d_pct": discount_vs_90d,
                    "deal_score": score,
                    "confidence": confidence,
                    "publication_status": status,
                    "best_title": best["title"],
                    "best_url": best["url"],
                    "offer_count": len(prices),
                }
            )
    rows.sort(key=lambda row: (row["deal_score"], row["discount_vs_market_pct"] or 0), reverse=True)
    return rows


def latest_deal_report(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            de.evaluated_at,
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
            de.publication_status,
            o.title AS best_title,
            o.url AS best_url
        FROM deal_evaluations de
        JOIN canonical_products cp ON cp.id = de.product_id
        LEFT JOIN offers o ON o.id = de.best_offer_id
        WHERE de.run_id = (SELECT MAX(id) FROM collection_runs WHERE status = 'success')
        ORDER BY de.deal_score DESC, de.discount_vs_market_pct DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
