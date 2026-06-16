ALTER TABLE deal_posts
ADD COLUMN source_category TEXT;

ALTER TABLE deal_posts
ADD COLUMN sale_starts_at TEXT;

ALTER TABLE deal_posts
ADD COLUMN sale_ends_at TEXT;

CREATE INDEX IF NOT EXISTS idx_deal_posts_sale_window
ON deal_posts(sale_starts_at, sale_ends_at);
