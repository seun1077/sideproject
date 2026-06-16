from __future__ import annotations

from pathlib import Path

from lxml import html

from ..deal_period import parse_sale_period
from ..http import fetch
from ..models import DealPostCandidate, ProductSeed
from ..repository import seed_key
from ..text_utils import clean, parse_price
from .deal_match import best_seed_match, looks_like_beauty_deal


RULIWEB_HOTDEAL_URL = "https://bbs.ruliweb.com/market/board/1020"
RULIWEB_CATEGORIES = (
    "게임S/W",
    "게임H/W",
    "PC/가전",
    "A/V",
    "VR",
    "음식",
    "의류",
    "취미용품",
    "인테리어",
    "생활용품",
    "육아용품",
    "레저용품",
    "휴대폰",
    "도서",
    "화장품",
    "상품권",
)


def _row_text(anchor) -> str:
    row = anchor.xpath("ancestor::tr[1]")
    if row:
        return clean(" ".join(row[0].xpath(".//text()")))
    return clean(anchor.text_content())


def _category(context: str) -> str | None:
    for category in RULIWEB_CATEGORIES:
        if category in context:
            return category
    return None


def collect_ruliweb_deals(
    seeds: list[ProductSeed],
    raw_path: Path | None = None,
) -> list[DealPostCandidate]:
    status, body, error = fetch(RULIWEB_HOTDEAL_URL)
    if status != 200 or not body:
        return []

    if raw_path:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(body, encoding="utf-8")

    doc = html.fromstring(body)
    posts: list[DealPostCandidate] = []
    seen: set[str] = set()
    for anchor in doc.xpath("//a[contains(@href, '/market/board/1020/read/')]"):
        href = (anchor.get("href") or "").split("#", 1)[0]
        if href in seen:
            continue
        title = clean(" ".join(anchor.xpath(".//text()")))
        if not title or title.startswith("루리웹 핫딜/예판"):
            continue
        context = _row_text(anchor)
        category = _category(context)
        if category != "화장품" and not looks_like_beauty_deal(context):
            continue
        price = parse_price(context) or parse_price(title)
        best_seed, match_score, matched_keywords = best_seed_match(context, seeds)
        sale_starts_at, sale_ends_at = parse_sale_period(context)
        seen.add(href)
        posts.append(
            DealPostCandidate(
                source_code="ruliweb",
                product_key=seed_key(best_seed) if best_seed else None,
                title=title[:240],
                url=href,
                extracted_price_krw=price,
                matched_keywords=",".join(matched_keywords[:8]),
                match_score=match_score,
                source_category=category,
                sale_starts_at=sale_starts_at,
                sale_ends_at=sale_ends_at,
                raw_payload={
                    "http_status": status,
                    "error": error,
                    "context": context[:500],
                    "board_url": RULIWEB_HOTDEAL_URL,
                },
            )
        )
    return posts
