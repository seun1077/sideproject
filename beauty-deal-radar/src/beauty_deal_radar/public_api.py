from __future__ import annotations

import sqlite3


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _deal_basis(row: sqlite3.Row) -> tuple[str, float | None, int | None]:
    if row["discount_vs_30d_pct"] is not None:
        return "30d", float(row["discount_vs_30d_pct"]), _optional_int(row["historical_median_30d_krw"])
    if row["discount_vs_market_pct"] is not None:
        return "market", float(row["discount_vs_market_pct"]), _optional_int(row["market_median_price_krw"])
    return "unknown", None, None


def _price_gap(current_price: int | None, reference_price: int | None) -> int | None:
    if current_price is None or reference_price is None:
        return None
    return reference_price - current_price


def _offer_options(
    conn: sqlite3.Connection,
    product_id: int,
    run_id: int,
    *,
    exclude_offer_id: int | None = None,
    limit: int = 4,
    approved_only: bool = False,
) -> list[dict]:
    params: list[object] = [run_id, product_id]
    exclude_sql = ""
    if exclude_offer_id is not None:
        exclude_sql = "AND o.id != ?"
        params.append(exclude_offer_id)
    status_sql = "AND o.match_status = 'approved'" if approved_only else "AND o.match_status IN ('candidate', 'approved')"
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
            o.id,
            o.title,
            o.url,
            ps.package_price_krw,
            ps.normalized_price_krw,
            o.pack_count,
            s.display_name AS source
        FROM price_snapshots ps
        JOIN offers o ON o.id = ps.offer_id
        JOIN sources s ON s.id = o.source_id
        WHERE ps.run_id = ?
          AND ps.product_id = ?
          {exclude_sql}
          AND o.baseline_eligible = 1
          AND ps.normalized_price_krw IS NOT NULL
          {status_sql}
        ORDER BY ps.normalized_price_krw ASC, ps.package_price_krw ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        {
            "offer_id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "source": row["source"],
            "package_price_krw": _optional_int(row["package_price_krw"]),
            "unit_price_krw": _optional_int(row["normalized_price_krw"]),
            "pack_count": _optional_int(row["pack_count"]),
        }
        for row in rows
    ]


def service_summary(conn: sqlite3.Connection) -> dict:
    latest_run = conn.execute(
        """
        SELECT id, started_at, finished_at, status, seed_count, offer_count, deal_post_count
        FROM collection_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    latest_success = conn.execute(
        """
        SELECT id, finished_at
        FROM collection_runs
        WHERE status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return {
        "latest_run": dict(latest_run) if latest_run else None,
        "latest_success": dict(latest_success) if latest_success else None,
        "products": conn.execute("SELECT COUNT(*) FROM canonical_products").fetchone()[0],
        "offers": conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0],
        "price_snapshots": conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0],
        "published_deals": conn.execute(
            "SELECT COUNT(*) FROM published_deals WHERE status = 'published'"
        ).fetchone()[0],
        "deal_candidates": conn.execute("SELECT COUNT(*) FROM deal_evaluations").fetchone()[0],
        "source_deal_candidates": conn.execute(
            "SELECT COUNT(*) FROM deal_posts WHERE match_status = 'candidate'"
        ).fetchone()[0],
        "approved_source_deals": conn.execute(
            "SELECT COUNT(*) FROM deal_posts WHERE match_status = 'approved'"
        ).fetchone()[0],
    }


def list_deals(
    conn: sqlite3.Connection,
    *,
    limit: int = 30,
    category: str | None = None,
    min_discount: float | None = None,
    visibility: str = "all",
) -> list[dict]:
    where = ["de.run_id = (SELECT MAX(id) FROM collection_runs WHERE status = 'success')"]
    params: list[object] = []
    if category:
        where.append("cp.category = ?")
        params.append(category)
    if min_discount is not None:
        where.append(
            """
            COALESCE(
                de.discount_vs_30d_pct,
                de.discount_vs_market_pct,
                de.discount_vs_90d_pct,
                0
            ) >= ?
            """
        )
        params.append(min_discount)
    if visibility == "public":
        where.append("(pd.status = 'published' OR de.publication_status = 'approved')")
        where.append("o.match_status = 'approved'")
        where.append("o.baseline_eligible = 1")
    elif visibility == "review":
        where.append("de.publication_status IN ('needs_review', 'draft')")

    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
            de.id AS evaluation_id,
            de.run_id,
            de.evaluated_at,
            de.publication_status,
            de.current_min_price_krw,
            de.market_median_price_krw,
            de.historical_median_30d_krw,
            de.historical_median_90d_krw,
            de.discount_vs_market_pct,
            de.discount_vs_30d_pct,
            de.discount_vs_90d_pct,
            de.deal_score,
            de.confidence,
            cp.id AS product_id,
            cp.brand,
            cp.name AS product,
            cp.category,
            cp.target_volume_value,
            cp.target_volume_unit,
            o.title AS best_title,
            o.url AS best_url,
            o.id AS offer_id,
            o.package_price_krw,
            o.normalized_price_krw,
            o.pack_count,
            s.display_name AS source,
            pd.id AS published_deal_id,
            pd.status AS published_status
        FROM deal_evaluations de
        JOIN canonical_products cp ON cp.id = de.product_id
        LEFT JOIN offers o ON o.id = de.best_offer_id
        LEFT JOIN sources s ON s.id = o.source_id
        LEFT JOIN published_deals pd ON pd.deal_evaluation_id = de.id
        WHERE {" AND ".join(where)}
        ORDER BY
            CASE
                WHEN pd.status = 'published' THEN 0
                WHEN de.publication_status = 'approved' THEN 1
                WHEN de.publication_status = 'auto_approved' THEN 2
                WHEN de.publication_status = 'needs_review' THEN 3
                ELSE 4
            END,
            de.deal_score DESC,
            COALESCE(de.discount_vs_30d_pct, de.discount_vs_market_pct, 0) DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    deals: list[dict] = []
    for row in rows:
        basis, discount, reference_price = _deal_basis(row)
        current_price = _optional_int(row["current_min_price_krw"])
        options = _offer_options(
            conn,
            int(row["product_id"]),
            int(row["run_id"]),
            exclude_offer_id=_optional_int(row["offer_id"]),
            approved_only=visibility == "public",
        )
        cheaper_options = [
            option
            for option in options
            if option["unit_price_krw"] is not None
            and current_price is not None
            and option["unit_price_krw"] < current_price
        ]
        deals.append(
            {
                "evaluation_id": row["evaluation_id"],
                "product_id": row["product_id"],
                "brand": row["brand"],
                "product": row["product"],
                "category": row["category"],
                "volume": (
                    f"{row['target_volume_value']:g}{row['target_volume_unit']}"
                    if row["target_volume_value"] and row["target_volume_unit"]
                    else None
                ),
                "title": row["best_title"],
                "url": row["best_url"],
                "source": row["source"],
                "current_price_krw": current_price,
                "package_price_krw": _optional_int(row["package_price_krw"]),
                "reference_price_krw": reference_price,
                "price_gap_krw": _price_gap(current_price, reference_price),
                "discount_pct": discount,
                "discount_basis": basis,
                "discount_vs_market_pct": _optional_float(row["discount_vs_market_pct"]),
                "discount_vs_30d_pct": _optional_float(row["discount_vs_30d_pct"]),
                "discount_vs_90d_pct": _optional_float(row["discount_vs_90d_pct"]),
                "deal_score": int(row["deal_score"]),
                "confidence": row["confidence"],
                "publication_status": row["publication_status"],
                "is_published": row["published_status"] == "published",
                "evaluated_at": row["evaluated_at"],
                "pack_count": _optional_int(row["pack_count"]),
                "other_options": options,
                "cheaper_options": cheaper_options,
            }
        )
    return deals


def list_source_deals(
    conn: sqlite3.Connection,
    *,
    limit: int = 30,
    category: str | None = None,
    min_discount: float | None = None,
    visibility: str = "all",
) -> list[dict]:
    where = ["1 = 1"]
    params: list[object] = []
    if category:
        where.append("cp.category = ?")
        params.append(category)
    if visibility == "public":
        where.append("dp.match_status = 'approved'")
    elif visibility == "review":
        where.append("dp.match_status = 'candidate'")
    rows = conn.execute(
        f"""
        WITH latest_success AS (
            SELECT MAX(id) AS run_id
            FROM collection_runs
            WHERE status = 'success'
        )
        SELECT
            dp.id AS source_deal_id,
            dp.product_id,
            dp.title,
            dp.url,
            dp.collected_at,
            dp.extracted_price_krw,
            dp.match_score,
            dp.match_status,
            s.display_name AS source,
            cp.brand,
            cp.name AS product,
            cp.category,
            cp.target_volume_value,
            cp.target_volume_unit,
            de.run_id,
            de.current_min_price_krw,
            de.market_median_price_krw,
            de.historical_median_30d_krw,
            de.historical_median_90d_krw,
            de.deal_score,
            de.confidence
        FROM deal_posts dp
        JOIN sources s ON s.id = dp.source_id
        LEFT JOIN canonical_products cp ON cp.id = dp.product_id
        LEFT JOIN latest_success ls ON 1 = 1
        LEFT JOIN deal_evaluations de
          ON de.product_id = dp.product_id
         AND de.run_id = ls.run_id
        WHERE {" AND ".join(where)}
        ORDER BY
            CASE dp.match_status WHEN 'approved' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END,
            dp.collected_at DESC,
            dp.match_score DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()

    deals: list[dict] = []
    for row in rows:
        deal_price = _optional_int(row["extracted_price_krw"])
        if row["historical_median_30d_krw"] is not None:
            reference_price = _optional_int(row["historical_median_30d_krw"])
            basis = "30d"
        elif row["market_median_price_krw"] is not None:
            reference_price = _optional_int(row["market_median_price_krw"])
            basis = "market"
        else:
            reference_price = _optional_int(row["current_min_price_krw"])
            basis = "current"
        discount = None
        if deal_price is not None and reference_price is not None and reference_price > 0:
            discount = round((reference_price - deal_price) / reference_price * 100, 1)
        if min_discount is not None and (discount is None or discount < min_discount):
            continue
        run_id = _optional_int(row["run_id"])
        product_id = _optional_int(row["product_id"])
        options = (
            _offer_options(
                conn,
                product_id,
                run_id,
                limit=3,
                approved_only=visibility == "public",
            )
            if product_id is not None and run_id is not None
            else []
        )
        deals.append(
            {
                "source_deal_id": row["source_deal_id"],
                "product_id": row["product_id"],
                "brand": row["brand"],
                "product": row["product"],
                "category": row["category"],
                "volume": (
                    f"{row['target_volume_value']:g}{row['target_volume_unit']}"
                    if row["target_volume_value"] and row["target_volume_unit"]
                    else None
                ),
                "title": row["title"],
                "url": row["url"],
                "source": row["source"],
                "current_price_krw": deal_price,
                "package_price_krw": deal_price,
                "reference_price_krw": reference_price,
                "price_gap_krw": _price_gap(deal_price, reference_price),
                "discount_pct": discount,
                "discount_basis": basis,
                "deal_score": _optional_int(row["deal_score"]) or int(row["match_score"] or 0),
                "confidence": row["confidence"],
                "publication_status": row["match_status"],
                "is_published": row["match_status"] == "approved",
                "evaluated_at": row["collected_at"],
                "other_options": options,
                "cheaper_options": [
                    option
                    for option in options
                    if option["unit_price_krw"] is not None
                    and deal_price is not None
                    and option["unit_price_krw"] < deal_price
                ],
            }
        )
    return deals


def list_products(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            cp.id,
            cp.brand,
            cp.name,
            cp.category,
            cp.target_volume_value,
            cp.target_volume_unit,
            cp.status,
            de.current_min_price_krw,
            de.market_median_price_krw,
            de.discount_vs_market_pct,
            de.discount_vs_30d_pct,
            de.deal_score,
            de.confidence,
            MAX(ps.collected_at) AS last_collected_at,
            COUNT(ps.id) AS snapshot_count
        FROM canonical_products cp
        LEFT JOIN deal_evaluations de
          ON de.product_id = cp.id
         AND de.run_id = (SELECT MAX(id) FROM collection_runs WHERE status = 'success')
        LEFT JOIN price_snapshots ps ON ps.product_id = cp.id
        WHERE cp.status = 'active'
        GROUP BY cp.id
        ORDER BY cp.category ASC, cp.brand ASC, cp.name ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    products: list[dict] = []
    for row in rows:
        products.append(
            {
                "id": row["id"],
                "brand": row["brand"],
                "product": row["name"],
                "category": row["category"],
                "volume": (
                    f"{row['target_volume_value']:g}{row['target_volume_unit']}"
                    if row["target_volume_value"] and row["target_volume_unit"]
                    else None
                ),
                "status": row["status"],
                "current_price_krw": _optional_int(row["current_min_price_krw"]),
                "market_median_price_krw": _optional_int(row["market_median_price_krw"]),
                "discount_vs_market_pct": _optional_float(row["discount_vs_market_pct"]),
                "discount_vs_30d_pct": _optional_float(row["discount_vs_30d_pct"]),
                "deal_score": _optional_int(row["deal_score"]),
                "confidence": row["confidence"],
                "last_collected_at": row["last_collected_at"],
                "snapshot_count": int(row["snapshot_count"]),
            }
        )
    return products


def price_history(conn: sqlite3.Connection, product_id: int, *, days: int = 90) -> list[dict]:
    rows = conn.execute(
        """
        SELECT stat_date, min_price_krw, median_price_krw, max_price_krw, offer_count, approved_offer_count
        FROM daily_product_price_stats
        WHERE product_id = ?
          AND stat_date >= date('now', ?)
        ORDER BY stat_date ASC
        """,
        (product_id, f"-{days} day"),
    ).fetchall()
    return [
        {
            "date": row["stat_date"],
            "min_price_krw": _optional_int(row["min_price_krw"]),
            "median_price_krw": _optional_int(row["median_price_krw"]),
            "max_price_krw": _optional_int(row["max_price_krw"]),
            "offer_count": int(row["offer_count"]),
            "approved_offer_count": int(row["approved_offer_count"]),
        }
        for row in rows
    ]


def categories(conn: sqlite3.Connection) -> list[str]:
    return [
        row["category"]
        for row in conn.execute(
            """
            SELECT DISTINCT category
            FROM canonical_products
            WHERE status = 'active'
            ORDER BY category ASC
            """
        ).fetchall()
    ]
