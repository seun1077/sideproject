from __future__ import annotations

import urllib.parse
from pathlib import Path

from lxml import html

from ..http import fetch
from ..models import DealPostCandidate, ProductSeed
from ..repository import seed_key
from ..text_utils import clean, parse_price


GENERIC_MATCH_TOKENS = {
    "크림",
    "세럼",
    "토너",
    "패드",
    "앰플",
    "선크림",
    "수분",
    "진정",
    "흔적",
    "그린",
    "마일드",
    "플러스",
    "에센스",
}


def _tokens(value: str) -> set[str]:
    return {
        token.strip()
        for token in value.split()
        if len(token.strip()) >= 2 and token.strip() not in GENERIC_MATCH_TOKENS
    }


def _match_seed(title: str, seed: ProductSeed) -> tuple[int, list[str]]:
    brand_tokens = _tokens(seed.brand)
    product_tokens = _tokens(seed.product) | _tokens(seed.query)
    matched_brand = sorted(token for token in brand_tokens if token in title)
    matched_product = sorted(token for token in product_tokens if token in title)
    if not matched_brand and len(matched_product) < 2:
        return 0, []
    score = min(100, len(matched_brand) * 55 + len(matched_product) * 18)
    return score, [*matched_brand, *matched_product]


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
        matches = [(seed, *_match_seed(title, seed)) for seed in seeds]
        matches = [(seed, score, keywords) for seed, score, keywords in matches if score > 0]
        if not matches:
            continue
        if href.startswith("/"):
            href = urllib.parse.urljoin("https://www.algumon.com", href)
        key = (title, href)
        if key in seen:
            continue
        seen.add(key)
        best_seed, match_score, matched_keywords = max(matches, key=lambda row: row[1])
        posts.append(
            DealPostCandidate(
                source_code="algumon",
                product_key=seed_key(best_seed),
                title=title[:240],
                url=href,
                extracted_price_krw=parse_price(title),
                matched_keywords=",".join(matched_keywords[:8]),
                match_score=match_score,
                raw_payload={"http_status": status, "error": error},
            )
        )
    return posts
