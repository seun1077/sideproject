ALTER TABLE deal_evaluations
ADD COLUMN publication_status TEXT NOT NULL DEFAULT 'draft'
CHECK (publication_status IN ('draft', 'auto_approved', 'needs_review', 'approved', 'rejected', 'expired'));

ALTER TABLE deal_evaluations
ADD COLUMN publication_note TEXT;

CREATE TABLE IF NOT EXISTS daily_product_price_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES canonical_products(id) ON DELETE CASCADE,
    stat_date TEXT NOT NULL,
    source_scope TEXT NOT NULL DEFAULT 'all',
    min_price_krw INTEGER,
    median_price_krw INTEGER,
    max_price_krw INTEGER,
    offer_count INTEGER NOT NULL DEFAULT 0,
    approved_offer_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (product_id, stat_date, source_scope)
);

CREATE INDEX IF NOT EXISTS idx_daily_product_price_stats_product_date
ON daily_product_price_stats(product_id, stat_date);

CREATE TABLE IF NOT EXISTS review_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL CHECK (target_type IN ('offer', 'deal_evaluation')),
    target_id INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve_match', 'reject_match', 'exclude', 'approve_deal', 'reject_deal', 'hold')),
    reason TEXT,
    decided_by TEXT NOT NULL DEFAULT 'admin',
    decided_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_review_decisions_target
ON review_decisions(target_type, target_id, decided_at DESC);

CREATE TABLE IF NOT EXISTS published_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_evaluation_id INTEGER NOT NULL REFERENCES deal_evaluations(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES canonical_products(id) ON DELETE CASCADE,
    offer_id INTEGER REFERENCES offers(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    current_price_krw INTEGER,
    discount_pct REAL,
    deal_score INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'expired', 'hidden')),
    published_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expired_at TEXT,
    UNIQUE (deal_evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_published_deals_status_score
ON published_deals(status, deal_score DESC, published_at DESC);

