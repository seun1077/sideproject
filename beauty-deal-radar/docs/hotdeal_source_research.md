# Hotdeal Source Research

Checked at: 2026-06-16 KST

The MVP should treat community hotdeal posts as the primary deal source, and use price-comparison sites as baseline evidence. Source collection priority is based on whether the board is reachable, whether list pages expose title/category/price/date in HTML, and whether beauty/skincare filtering is possible without logging in.

## Current Priority

| Source | URL | Status | Notes |
| --- | --- | --- | --- |
| Algumon | https://www.algumon.com/n/deal | Active | Aggregates Ppomppu, Ruliweb, Quasarzone, Clien, Arca, and others. Has category/site/period filters in the visible page. Already collected. |
| TheQoo Ddeokdeal | https://theqoo.net/theqdeal | Active, cautious | Public list is reachable. Parser should keep only beauty/skincare terms or known product matches. Some responses look bot-sensitive, so keep conservative fetch rate. Already collected. |
| Ruliweb Hotdeal | https://bbs.ruliweb.com/market/board/1020 | Active | Public list is reachable and exposes categories including cosmetics. Add direct collector. |
| Ppomppu | https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu | Candidate | Public page reachable. Needs parser and beauty filtering. |
| FMKorea Hotdeal | https://www.fmkorea.com/hotdeal | Candidate | Public page reachable. Needs parser and beauty filtering. |
| Clien Jirum | https://www.clien.net/service/board/jirum | Candidate | Public page reachable. Needs parser and beauty filtering. |
| Coolenjoy Jirum | https://coolenjoy.net/bbs/jirum | Candidate | Public page reachable. Needs parser and beauty filtering. |
| Quasarzone Saleinfo | https://quasarzone.com/bbs/qb_saleinfo | Cautious | Page responds but showed bot/JS risk hints. Add only after parser stability check. |
| Arca Hotdeal | https://arca.live/b/hotdeal | Cautious | Page responds but showed bot/JS risk hints. Add only after parser stability check. |
| Dealbada Domestic | https://www.dealbada.com/bbs/board.php?bo_table=deal_domestic | Blocked/slow | Timed out in probe. Defer. |
| X/Twitter | https://x.com | Defer | Search requires API/login for reliability. Do not scrape timeline HTML as MVP dependency. |

## Date Policy

Sale date text must be interpreted relative to the collection timestamp in Korea time.

- `6/17`, `6월17일`: 2026-06-17 when collected on 2026-06-16 KST.
- `6/15~6/20`, `6월15일~6월20일`: start/end dates in the current Korean year unless the date is more than 60 days behind the collection date.
- `오늘`, `단 하루`, `일일특가`: collection date in Korea time.
- Missing sale period is allowed, but admin should show `기간 정보 없음`.

## Filtering Policy

For the skincare MVP, source posts should enter the admin queue only when:

- The source category is explicitly cosmetics/beauty, or
- The title/context includes beauty/skincare terms, or
- It matches a known tracked product/brand with enough score.

General lifestyle deals such as kitchenware, food, appliances, gift cards, and phone plans should not enter the skincare source queue.
