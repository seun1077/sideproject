# Beauty Deal Radar

Prototype data collector for a skincare-focused hot-deal and price judgment service.

## What this prototype checks

- Whether public deal aggregators expose enough skincare/cosmetics deal text to filter.
- Whether price comparison pages can provide a usable current-price baseline.
- How to turn one-day market prices into a rough deal score before user traffic exists.

## Current data policy

This prototype only performs polite, low-volume collection from public pages that were reachable during testing.

- Algumon: `robots.txt` allowed public pages except `/api`, `/session`, `/l/d/`. The script does not call blocked API paths.
- Danawa: public search pages were reachable and its robots file describes broad public-page access with selected disallows.
- Olive Young: direct automated access returned a Cloudflare challenge page, so it is recorded as blocked and skipped.
- Musinsa: robots was reachable, but marketplace/product crawling should be treated as partner/API-only until the exact allowed paths are reviewed.

For a production service, prefer official affiliate feeds, partner APIs, user submissions, and explicit partnerships over broad scraping.

## Run

Use the bundled Python from Codex if system Python is unavailable:

```powershell
C:\Users\ynkim\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\manage.py init-db
C:\Users\ynkim\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\manage.py collect
C:\Users\ynkim\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\manage.py report
C:\Users\ynkim\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\manage.py review-queue
C:\Users\ynkim\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\manage.py admin-server
```

The legacy shortcut still works:

```powershell
C:\Users\ynkim\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\collect.py
```

The SQLite database is written to `data/beauty_deals.sqlite3`.
CSV/JSON snapshots are written under `data/processed`.
Raw HTML is only stored when `--keep-raw` is passed.

## Admin Page

Run the local admin server:

```powershell
C:\Users\ynkim\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\manage.py admin-server --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765/
```

The admin page can:

- run today's collection pipeline
- show deal evaluations and publication status
- open source/search links for manual verification
- approve or reject deal publication
- approve, reject, or exclude offer-product matches

## Backend Structure

- `migrations/`: SQL schema migrations.
- `src/beauty_deal_radar/collectors/`: source-specific collectors.
- `src/beauty_deal_radar/repository.py`: SQLite writes and upserts.
- `src/beauty_deal_radar/evaluation.py`: deal scoring.
- `src/beauty_deal_radar/admin.py`: review queue queries.
- `src/beauty_deal_radar/web_admin.py`: local admin web UI.
- `docs/backend_architecture.md`: data model notes.

## Baseline logic

With no user history yet, the prototype uses the current Danawa search-result distribution as a temporary baseline:

- `current_min_price`: lowest matched price normalized to one seed-size item.
- `market_median_price`: median of matched prices normalized to one seed-size item.
- `discount_vs_median_pct`: how much cheaper the lowest price is than the current search-result median.

This is not a true historical discount. It is a bootstrap proxy until the service accumulates daily snapshots.

The collector also records:

- `match_score`
- `excluded_reason`
- `usable_for_baseline`
- `pack_count`
- `normalized_price_krw`
- parsed volume fields

These fields are intentionally visible because product matching is the core risk in this business.
