from __future__ import annotations

import urllib.parse
from pathlib import Path

from lxml import html

from ..http import fetch
from ..models import DealPostCandidate, ProductSeed
from ..repository import seed_key
from ..text_utils import clean, parse_price
from .deal_match import best_seed_match, looks_like_beauty_deal


THEQOO_DEAL_URL = "https://theqoo.net/theqdeal"


def _candidate_text(anchor) -> str:
    row = anchor.xpath("ancestor::tr[1]")
    if row:
        return clean(" ".join(row[0].xpath(".//text()")))
    parent = anchor.getparent()
    return clean(" ".join(parent.xpath(".//text()"))) if parent is not None else clean(anchor.text_content())


def collect_theqoo_deals(
    seeds: list[ProductSeed],
    raw_path: Path | None = None,
) -> list[DealPostCandidate]:
    status, body, error = fetch(THEQOO_DEAL_URL)
    if status != 200 or not body:
        return []

    if raw_path:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(body, encoding="utf-8")

    doc = html.fromstring(body)
    posts: list[DealPostCandidate] = []
    seen: set[str] = set()
    for anchor in doc.xpath("//a[@href]"):
        href = anchor.get("href") or ""
        if "/theqdeal/" not in href:
            continue
        title = clean(" ".join(anchor.xpath(".//text()")))
        if not title or title in {"목록", "HOT 게시물"}:
            continue
        if len(title) < 8 and parse_price(title) is None:
            continue
        if title.endswith(")") and parse_price(title) is None:
            continue
        context = _candidate_text(anchor)
        price = parse_price(context) or parse_price(title)
        if not price:
            continue
        best_seed, match_score, matched_keywords = best_seed_match(context, seeds)
        if best_seed is None and not looks_like_beauty_deal(context):
            continue
        url = urllib.parse.urljoin(THEQOO_DEAL_URL, href)
        if url in seen:
            continue
        seen.add(url)
        posts.append(
            DealPostCandidate(
                source_code="theqoo",
                product_key=seed_key(best_seed) if best_seed else None,
                title=title[:240],
                url=url,
                extracted_price_krw=price,
                matched_keywords=",".join(matched_keywords[:8]),
                match_score=match_score,
                raw_payload={
                    "http_status": status,
                    "error": error,
                    "context": context[:500],
                    "board_url": THEQOO_DEAL_URL,
                },
            )
        )
    return posts
