CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('marketplace', 'deal_aggregator', 'community', 'affiliate', 'manual')),
    base_url TEXT,
    robots_url TEXT,
    collection_policy TEXT NOT NULL DEFAULT 'unknown',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS canonical_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key TEXT NOT NULL UNIQUE,
    brand TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    target_volume_value REAL,
    target_volume_unit TEXT,
    canonical_query TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'watching', 'inactive')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS product_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES canonical_products(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'keyword' CHECK (alias_type IN ('keyword', 'brand_alias', 'option_alias', 'exclude_keyword')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (product_id, alias, alias_type)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    collector_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    seed_count INTEGER NOT NULL DEFAULT 0,
    offer_count INTEGER NOT NULL DEFAULT 0,
    deal_post_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS source_access_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES collection_runs(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    checked_at TEXT NOT NULL,
    url TEXT NOT NULL,
    http_status INTEGER,
    response_bytes INTEGER,
    looks_blocked INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    snippet TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    source_offer_key TEXT NOT NULL,
    product_id INTEGER REFERENCES canonical_products(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    seller_name TEXT,
    brand_hint TEXT,
    category_hint TEXT,
    package_price_krw INTEGER,
    normalized_price_krw INTEGER,
    currency TEXT NOT NULL DEFAULT 'KRW',
    volume_value REAL,
    volume_unit TEXT,
    pack_count INTEGER NOT NULL DEFAULT 1,
    condition_type TEXT NOT NULL DEFAULT 'new' CHECK (condition_type IN ('new', 'used', 'unknown')),
    match_score INTEGER NOT NULL DEFAULT 0,
    match_status TEXT NOT NULL DEFAULT 'candidate' CHECK (match_status IN ('candidate', 'approved', 'rejected', 'excluded')),
    exclusion_reason TEXT,
    baseline_eligible INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_payload TEXT,
    UNIQUE (source_id, source_offer_key)
);

CREATE INDEX IF NOT EXISTS idx_offers_product_status ON offers(product_id, match_status, baseline_eligible);
CREATE INDEX IF NOT EXISTS idx_offers_last_seen ON offers(last_seen_at);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES collection_runs(id) ON DELETE SET NULL,
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES canonical_products(id) ON DELETE SET NULL,
    collected_at TEXT NOT NULL,
    package_price_krw INTEGER,
    normalized_price_krw INTEGER,
    shipping_fee_krw INTEGER,
    coupon_discount_krw INTEGER,
    point_value_krw INTEGER,
    availability TEXT NOT NULL DEFAULT 'unknown' CHECK (availability IN ('in_stock', 'sold_out', 'unknown')),
    raw_payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_product_time ON price_snapshots(product_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_price_snapshots_offer_time ON price_snapshots(offer_id, collected_at);

CREATE TABLE IF NOT EXISTS deal_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    source_post_key TEXT NOT NULL,
    product_id INTEGER REFERENCES canonical_products(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    posted_at TEXT,
    collected_at TEXT NOT NULL,
    extracted_price_krw INTEGER,
    matched_keywords TEXT,
    match_score INTEGER NOT NULL DEFAULT 0,
    match_status TEXT NOT NULL DEFAULT 'candidate' CHECK (match_status IN ('candidate', 'approved', 'rejected', 'excluded')),
    raw_payload TEXT,
    UNIQUE (source_id, source_post_key)
);

CREATE INDEX IF NOT EXISTS idx_deal_posts_product_time ON deal_posts(product_id, collected_at);

CREATE TABLE IF NOT EXISTS deal_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES collection_runs(id) ON DELETE SET NULL,
    product_id INTEGER NOT NULL REFERENCES canonical_products(id) ON DELETE CASCADE,
    best_offer_id INTEGER REFERENCES offers(id) ON DELETE SET NULL,
    evaluated_at TEXT NOT NULL,
    current_min_price_krw INTEGER,
    market_median_price_krw INTEGER,
    historical_median_30d_krw INTEGER,
    historical_median_90d_krw INTEGER,
    discount_vs_market_pct REAL,
    discount_vs_30d_pct REAL,
    discount_vs_90d_pct REAL,
    deal_score INTEGER NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'low' CHECK (confidence IN ('low', 'medium', 'high')),
    reason TEXT,
    UNIQUE (run_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_deal_evaluations_score ON deal_evaluations(deal_score DESC, evaluated_at DESC);

