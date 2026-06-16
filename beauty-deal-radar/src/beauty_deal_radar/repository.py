from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3

from .models import DealPostCandidate, OfferCandidate, ProductSeed
from .text_utils import canonical_key, parse_volume


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_key(*parts: object) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seed_key(seed: ProductSeed) -> str:
    return canonical_key(seed.brand, seed.product, seed.volume_hint)


def upsert_default_sources(conn: sqlite3.Connection) -> None:
    sources = [
        ("danawa", "Danawa", "marketplace", "https://www.danawa.com", "https://www.danawa.com/robots.txt", "public_search_probe"),
        ("algumon", "Algumon", "deal_aggregator", "https://www.algumon.com", "https://www.algumon.com/robots.txt", "public_pages_no_api"),
        ("theqoo", "TheQoo Ddeokdeal", "community", "https://theqoo.net/theqdeal", "https://theqoo.net/robots.txt", "public_board_probe"),
        ("oliveyoung", "Olive Young", "marketplace", "https://www.oliveyoung.co.kr", "https://www.oliveyoung.co.kr/robots.txt", "blocked_skip"),
        ("musinsa", "Musinsa", "marketplace", "https://www.musinsa.com", "https://www.musinsa.com/robots.txt", "review_before_collect"),
    ]
    with conn:
        for row in sources:
            conn.execute(
                """
                INSERT INTO sources (code, display_name, source_type, base_url, robots_url, collection_policy)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    display_name=excluded.display_name,
                    source_type=excluded.source_type,
                    base_url=excluded.base_url,
                    robots_url=excluded.robots_url,
                    collection_policy=excluded.collection_policy,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                row,
            )


def get_source_id(conn: sqlite3.Connection, code: str) -> int:
    row = conn.execute("SELECT id FROM sources WHERE code = ?", (code,)).fetchone()
    if not row:
        raise ValueError(f"Unknown source: {code}")
    return int(row["id"])


def upsert_product(conn: sqlite3.Connection, seed: ProductSeed) -> int:
    volume = parse_volume(seed.volume_hint)
    key = seed_key(seed)
    with conn:
        conn.execute(
            """
            INSERT INTO canonical_products (
                canonical_key, brand, name, category, target_volume_value,
                target_volume_unit, canonical_query
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_key) DO UPDATE SET
                brand=excluded.brand,
                name=excluded.name,
                category=excluded.category,
                target_volume_value=excluded.target_volume_value,
                target_volume_unit=excluded.target_volume_unit,
                canonical_query=excluded.canonical_query,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                key,
                seed.brand,
                seed.product,
                seed.category,
                volume[0] if volume else None,
                volume[1] if volume else None,
                seed.query,
            ),
        )
        row = conn.execute(
            "SELECT id FROM canonical_products WHERE canonical_key = ?",
            (key,),
        ).fetchone()
        product_id = int(row["id"])
        for alias in {seed.brand, seed.product, seed.query, seed.category}:
            conn.execute(
                """
                INSERT OR IGNORE INTO product_aliases (product_id, alias, alias_type)
                VALUES (?, ?, 'keyword')
                """,
                (product_id, alias),
            )
    return product_id


def product_id_by_key(conn: sqlite3.Connection, key: str | None) -> int | None:
    if not key:
        return None
    row = conn.execute("SELECT id FROM canonical_products WHERE canonical_key = ?", (key,)).fetchone()
    return int(row["id"]) if row else None


def create_run(conn: sqlite3.Connection, collector_version: str, seed_count: int) -> int:
    started_at = utc_now()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO collection_runs (started_at, collector_version, seed_count)
            VALUES (?, ?, ?)
            """,
            (started_at, collector_version, seed_count),
        )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    offer_count: int,
    deal_post_count: int,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE collection_runs
            SET finished_at = ?, status = ?, offer_count = ?, deal_post_count = ?, error = ?
            WHERE id = ?
            """,
            (utc_now(), status, offer_count, deal_post_count, error, run_id),
        )


def record_source_check(conn: sqlite3.Connection, run_id: int, row: dict) -> None:
    source_id = get_source_id(conn, row["source_code"])
    with conn:
        conn.execute(
            """
            INSERT INTO source_access_checks (
                run_id, source_id, checked_at, url, http_status, response_bytes,
                looks_blocked, error, snippet
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_id,
                row["checked_at"],
                row["url"],
                row.get("status"),
                row.get("bytes"),
                1 if row.get("looks_blocked") else 0,
                row.get("error") or None,
                row.get("snippet") or None,
            ),
        )


def upsert_offer(conn: sqlite3.Connection, run_id: int, offer: OfferCandidate, collected_at: str) -> int:
    source_id = get_source_id(conn, offer.source_code)
    product_id = product_id_by_key(conn, offer.product_key)
    source_offer_key = stable_key(offer.source_code, offer.url, offer.title)
    with conn:
        conn.execute(
            """
            INSERT INTO offers (
                source_id, source_offer_key, product_id, title, url, brand_hint,
                category_hint, package_price_krw, normalized_price_krw, volume_value,
                volume_unit, pack_count, condition_type, match_score, match_status,
                exclusion_reason, baseline_eligible, first_seen_at, last_seen_at, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, source_offer_key) DO UPDATE SET
                product_id=excluded.product_id,
                title=excluded.title,
                url=excluded.url,
                package_price_krw=excluded.package_price_krw,
                normalized_price_krw=excluded.normalized_price_krw,
                volume_value=excluded.volume_value,
                volume_unit=excluded.volume_unit,
                pack_count=excluded.pack_count,
                condition_type=excluded.condition_type,
                match_score=excluded.match_score,
                match_status=excluded.match_status,
                exclusion_reason=excluded.exclusion_reason,
                baseline_eligible=excluded.baseline_eligible,
                last_seen_at=excluded.last_seen_at,
                raw_payload=excluded.raw_payload
            """,
            (
                source_id,
                source_offer_key,
                product_id,
                offer.title,
                offer.url,
                offer.package_price_krw,
                offer.normalized_price_krw,
                offer.volume_value,
                offer.volume_unit,
                offer.pack_count,
                "used" if "중고" in offer.title else "new",
                offer.match.score,
                offer.match.status,
                offer.match.exclusion_reason or None,
                1 if offer.match.baseline_eligible else 0,
                collected_at,
                collected_at,
                json.dumps(offer.raw_payload, ensure_ascii=False),
            ),
        )
        row = conn.execute(
            "SELECT id FROM offers WHERE source_id = ? AND source_offer_key = ?",
            (source_id, source_offer_key),
        ).fetchone()
        offer_id = int(row["id"])
        conn.execute(
            """
            INSERT INTO price_snapshots (
                run_id, offer_id, product_id, collected_at, package_price_krw,
                normalized_price_krw, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                offer_id,
                product_id,
                collected_at,
                offer.package_price_krw,
                offer.normalized_price_krw,
                json.dumps(offer.raw_payload, ensure_ascii=False),
            ),
        )
    return offer_id


def upsert_deal_post(conn: sqlite3.Connection, post: DealPostCandidate, collected_at: str) -> int:
    source_id = get_source_id(conn, post.source_code)
    product_id = product_id_by_key(conn, post.product_key)
    source_post_key = stable_key(post.source_code, post.url, post.title)
    with conn:
        conn.execute(
            """
            INSERT INTO deal_posts (
                source_id, source_post_key, product_id, title, url, collected_at,
                extracted_price_krw, matched_keywords, match_score, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, source_post_key) DO UPDATE SET
                product_id=excluded.product_id,
                title=excluded.title,
                url=excluded.url,
                collected_at=excluded.collected_at,
                extracted_price_krw=excluded.extracted_price_krw,
                matched_keywords=excluded.matched_keywords,
                match_score=excluded.match_score,
                raw_payload=excluded.raw_payload
            """,
            (
                source_id,
                source_post_key,
                product_id,
                post.title,
                post.url,
                collected_at,
                post.extracted_price_krw,
                post.matched_keywords,
                post.match_score,
                json.dumps(post.raw_payload, ensure_ascii=False),
            ),
        )
        row = conn.execute(
            "SELECT id FROM deal_posts WHERE source_id = ? AND source_post_key = ?",
            (source_id, source_post_key),
        ).fetchone()
    return int(row["id"])
