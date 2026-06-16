from __future__ import annotations

import urllib.parse
from pathlib import Path

from lxml import html

from ..deal_period import parse_sale_period
from ..http import fetch
from ..models import DealPostCandidate, ProductSeed
from ..repository import seed_key
from ..text_utils import clean, parse_price
from .deal_match import best_seed_match, looks_like_beauty_deal, match_seed as _match_seed


def collect_algumon_latest(
    seeds: list[ProductSeed],
    raw_path: Path | None = None,
) -> list[DealPostCandidate]:
    url = "https://www.algumon.com/n/deal"
    status, body, error = fetch(url)
    if status != 200 or not body:
        return []

    if raw_path:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(body, encoding="utf-8")

    doc = html.fromstring(body)
    posts: list[DealPostCandidate] = []
    seen = set()
    for anchor in doc.xpath("//a[@href]"):
        title = clean(" ".join(anchor.xpath(".//text()")))
        href = anchor.get("href")
        if not title or not href:
            continue
        best_seed, match_score, matched_keywords = best_seed_match(title, seeds)
        price = parse_price(title)
        if best_seed is None and not (price and looks_like_beauty_deal(title)):
            continue
        if href.startswith("/"):
            href = urllib.parse.urljoin("https://www.algumon.com", href)
        key = (title, href)
        if key in seen:
            continue
        seen.add(key)
        sale_starts_at, sale_ends_at = parse_sale_period(title)
        posts.append(
            DealPostCandidate(
                source_code="algumon",
                product_key=seed_key(best_seed) if best_seed else None,
                title=title[:240],
                url=href,
                extracted_price_krw=price,
                matched_keywords=",".join(matched_keywords[:8]),
                match_score=match_score,
                sale_starts_at=sale_starts_at,
                sale_ends_at=sale_ends_at,
                raw_payload={"http_status": status, "error": error},
            )
        )
    return posts
