# Backend Architecture

The backend is organized around stable product identity, not around crawler output.

## Core Flow

```text
canonical_products
  -> offers
  -> price_snapshots
  -> deal_evaluations
```

Community or aggregator posts follow a parallel path:

```text
canonical_products
  -> deal_posts
```

This lets us add new sources without changing the core product and deal judgment model.

## Tables

| Table | Purpose |
| --- | --- |
| `sources` | A registry of marketplaces, aggregators, communities, affiliate feeds, and manual inputs. |
| `canonical_products` | The canonical product the service understands, such as `라운드랩 자작나무 수분 선크림 50ml`. |
| `product_aliases` | Search keywords, brand aliases, option aliases, and later exclusion keywords. |
| `collection_runs` | One execution of the data pipeline. Useful for debugging, monitoring, and rollback. |
| `source_access_checks` | Robots/access/challenge checks for data-source health. |
| `offers` | Marketplace/shop result candidates. These can be matched, excluded, approved, or rejected. |
| `price_snapshots` | Time-series price observations. This is what eventually powers 30/90/180-day baselines. |
| `deal_posts` | Hot-deal/community posts. They may or may not have a parsed price. |
| `deal_evaluations` | The current judgment layer: best offer, market median, discount, score, confidence. |
| `daily_product_price_stats` | Daily product-level price summaries used for 30/90-day baselines and long-term storage control. |
| `review_decisions` | Human decisions for product matching and deal publication. |
| `published_deals` | Deals explicitly published by an admin or future automation. |

## Matching Principles

Do not trust crawler results blindly.

Each offer stores:

- `match_score`
- `match_status`
- `exclusion_reason`
- `baseline_eligible`
- parsed volume
- pack count
- original package price
- normalized one-item price

This keeps false positives visible and gives the admin UI a clean review queue.

## Migration Principles

- Every schema change must be a numbered SQL file under `migrations/`.
- App code should call `apply_migrations()` before writing data.
- Avoid one-off schema edits in scripts.

## Near-Term Product Decisions

The current deal score is a bootstrap score. It compares the best normalized current price against the current matched-result median.

Once daily snapshots exist, the score should prefer:

1. 90-day historical median
2. 30-day historical median
3. current matched-result median

The current median remains useful as a fallback when a product is newly added.

## Admin Workflow

Offer matching and deal publication are separate decisions.

```text
offer match approval
  = this marketplace result is the same canonical product

deal publication approval
  = today's price is worth showing as a hot deal
```

Approved offers keep contributing to future price snapshots.
Deal evaluations are recalculated every collection run because a valid product can be a hot deal today and a normal price tomorrow.
