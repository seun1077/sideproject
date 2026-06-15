CREATE TABLE IF NOT EXISTS source_deal_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_post_id INTEGER NOT NULL REFERENCES deal_posts(id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK (decision IN ('approve_source_deal', 'reject_source_deal', 'exclude_source_deal')),
    reason TEXT,
    decided_by TEXT NOT NULL DEFAULT 'admin',
    decided_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_source_deal_reviews_post
ON source_deal_reviews(deal_post_id, decided_at DESC);
