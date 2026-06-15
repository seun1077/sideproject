from __future__ import annotations

import math
import sqlite3
import statistics

from .repository import utc_now


def evaluate_current_deals(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    products = conn.execute(
        "SELECT id, brand, name, category, target_volume_value, target_volume_unit FROM canonical_products WHERE status = 'active'"
    ).fetchall()
    evaluated_at = utc_now()
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
            score = 50
            if discount_vs_market is not None:
                score = max(0, min(100, 50 + math.floor(discount_vs_market * 1.8)))
            confidence = "low"
            if len(prices) >= 6:
                confidence = "medium"
            if len(prices) >= 10:
                confidence = "high"
            best = offers[0]
            reason = "current_market_median_bootstrap"
            conn.execute(
                """
                INSERT INTO deal_evaluations (
                    run_id, product_id, best_offer_id, evaluated_at, current_min_price_krw,
                    market_median_price_krw, discount_vs_market_pct, deal_score,
                    confidence, reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, product_id) DO UPDATE SET
                    best_offer_id=excluded.best_offer_id,
                    evaluated_at=excluded.evaluated_at,
                    current_min_price_krw=excluded.current_min_price_krw,
                    market_median_price_krw=excluded.market_median_price_krw,
                    discount_vs_market_pct=excluded.discount_vs_market_pct,
                    deal_score=excluded.deal_score,
                    confidence=excluded.confidence,
                    reason=excluded.reason
                """,
                (
                    run_id,
                    product["id"],
                    best["id"],
                    evaluated_at,
                    current_min,
                    market_median,
                    discount_vs_market,
                    score,
                    confidence,
                    reason,
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
                    "discount_vs_market_pct": discount_vs_market,
                    "deal_score": score,
                    "confidence": confidence,
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
            de.discount_vs_market_pct,
            de.deal_score,
            de.confidence,
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

