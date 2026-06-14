# Collection Report

Snapshot: `20260614T072530Z`

## Summary

- Seed products: 20 popular skincare/cosmetics products.
- Danawa rows collected: 160 rows, 8 results per seed query.
- Price snapshots generated: 20 of 20 seed products.
- Deal candidates: 12 products with a current normalized price at least 15% below the matched-result median.
- Algumon latest-page keyword matches: 2 rows.

## Source Access

| Source | Result |
| --- | --- |
| Algumon robots | Allowed public pages; `/api`, `/session`, `/l/d/` disallowed. |
| Algumon latest page | Reachable as public SSR HTML; useful for broad latest-deal keyword filtering. |
| Danawa robots | Reachable; public search page usable in this low-volume prototype. |
| Danawa search | Reachable and yielded structured enough HTML for product titles/prices. |
| Olive Young | Returned HTTP 403 / Cloudflare challenge; skipped for automated collection. |
| Musinsa | Robots reachable, but product crawling should be reviewed path-by-path or handled through partnership/API. |

## Current Best Signals

The bootstrap baseline is not historical yet. It compares the current lowest matched result against the current matched-result median after basic product matching, volume filtering, and bundle normalization.

Top candidates from the latest run:

| Product | Normalized current price | Median baseline | Delta |
| --- | ---: | ---: | ---: |
| 넘버즈인 3번 보들보들 결 세럼 50ml | 13,710 | 33,775 | 59.4% below |
| 코스알엑스 스네일 96 에센스 100ml | 12,150 | 25,530 | 52.4% below |
| 라운드랩 1025 독도 토너 200ml | 9,550 | 18,475 | 48.3% below |
| 닥터지 그린 마일드 업 선 플러스 50ml | 7,800 normalized from bundle | 15,004 | 48.0% below |
| 조선미녀 맑은쌀 선크림 50ml | 8,400 | 14,615 | 42.5% below |
| 에뛰드 순정 2x 베리어 크림 60ml | 9,570 | 16,405 | 41.7% below |
| 토리든 다이브인 세럼 50ml | 12,910 | 21,702 | 40.5% below |
| 메디힐 마데카소사이드 패드 100매 | 21,930 | 33,240 | 34.0% below |
| 바이오더마 센시비오 H2O 500ml | 13,570 | 20,025 | 32.2% below |
| 마녀공장 퓨어 클렌징 오일 200ml | 15,370 | 22,165 | 30.7% below |

## What This Proves

The basic proposition is viable enough for a next build step:

- Famous-product seed lists can produce usable price candidates quickly.
- The hard part is not fetching pages; it is product matching, option matching, volume normalization, and bundle math.
- Direct crawling of major retailers like Olive Young is not a reliable starting point.
- A practical MVP should combine Danawa/search-style public baselines, community deal aggregators, user submissions, and affiliate/partner feeds.

## Immediate Next Steps

1. Add daily snapshots so `discount_vs_median_pct` can become a true 30/90/180-day historical comparison.
2. Add canonical product IDs and option groups, especially for refills, sets, renewed formulas, and volume variants.
3. Add official/affiliate sources before trying to collect protected retailer pages.
4. Build a small review UI for manually approving false positives in the first 500 products.

