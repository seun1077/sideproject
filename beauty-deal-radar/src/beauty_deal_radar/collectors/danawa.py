from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from lxml import html

from ..http import fetch
from ..matching import score_offer_match
from ..models import OfferCandidate, ProductSeed
from ..repository import seed_key
from ..text_utils import clean, parse_pack_count, parse_price, parse_volume


def parse_danawa_detail_page(body: str) -> tuple[str | None, int | None]:
    doc = html.fromstring(body)
    title_candidates = doc.xpath(
        "//meta[@name='Title']/@content | "
        "//meta[@property='og:title']/@content | "
        "//title/text()"
    )
    title = None
    for candidate in title_candidates:
        cleaned = clean(candidate)
        cleaned = re.sub(r"^\[?다나와\]?\s*", "", cleaned)
        cleaned = re.sub(r"\s*:\s*다나와\s*가격비교\s*$", "", cleaned)
        if cleaned:
            title = cleaned
            break

    price_candidates = doc.xpath(
        "//meta[@property='og:description']/@content | "
        "//meta[@name='Description']/@content"
    )
    price = None
    for candidate in price_candidates:
        price = parse_price(candidate)
        if price is not None:
            break
    return title, price


def fetch_danawa_detail(link: str) -> tuple[str | None, int | None]:
    parsed = urllib.parse.urlparse(link)
    if "prod.danawa.com" not in parsed.netloc or not parsed.path.startswith("/info/"):
        return None, None
    status, body, _error = fetch(link)
    if status != 200 or not body:
        return None, None
    return parse_danawa_detail_page(body)


def parse_danawa_item_price(item) -> int | None:
    price_texts = item.xpath(
        ".//*[contains(@class, 'price_sect') and "
        "not(contains(@class, 'memory_price_sect'))]//strong/text()"
    )
    prices: list[int] = []
    for text in price_texts:
        raw = re.sub(r"[^0-9]", "", text)
        if not raw:
            continue
        value = int(raw)
        if 500 <= value <= 2_000_000:
            prices.append(value)
    if prices:
        return prices[0]
    return parse_price(clean(" ".join(item.xpath(".//text()"))))


def collect_danawa_for_seed(
    seed: ProductSeed,
    limit: int = 8,
    raw_dir: Path | None = None,
    stamp: str | None = None,
) -> list[OfferCandidate]:
    url = "https://search.danawa.com/dsearch.php?" + urllib.parse.urlencode({"query": seed.query})
    status, body, error = fetch(url)
    if status != 200 or not body:
        return []

    if raw_dir and stamp:
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe_query = re.sub(r"[^0-9A-Za-z가-힣]+", "_", seed.query).strip("_")
        (raw_dir / f"{stamp}_{safe_query}.html").write_text(body, encoding="utf-8")

    doc = html.fromstring(body)
    items = doc.xpath(
        "//li[contains(@class, 'prod_item') or contains(@class, 'product_list_item')]"
    )
    if not items:
        items = doc.xpath("//div[contains(@class, 'prod_main_info')]/ancestor::li[1]")

    offers: list[OfferCandidate] = []
    seen = set()
    target_volume = parse_volume(seed.volume_hint)
    for item in items:
        title_nodes = item.xpath(
            ".//*[contains(@class, 'prod_name')]//a/text() | "
            ".//*[contains(@class, 'prod_name')]//text() | "
            ".//a[contains(@class, 'click_log_product_standard_title_')]/text()"
        )
        title = clean(" ".join(title_nodes))
        if not title:
            continue
        price = parse_danawa_item_price(item)
        links = item.xpath(".//*[contains(@class, 'prod_name')]//a/@href | .//a/@href")
        link = links[0] if links else url
        detail_title, detail_price = fetch_danawa_detail(link)
        if detail_title:
            title = detail_title
        if detail_price:
            price = detail_price
        key = (title, price, link)
        if key in seen:
            continue
        seen.add(key)
        title_volume = parse_volume(title)
        pack_count = parse_pack_count(title, target_volume)
        normalized_price = round(price / pack_count) if price and pack_count else price
        match = score_offer_match(seed, title)
        offers.append(
            OfferCandidate(
                source_code="danawa",
                product_key=seed_key(seed),
                title=title,
                url=link,
                package_price_krw=price,
                normalized_price_krw=normalized_price,
                volume_value=title_volume[0] if title_volume else None,
                volume_unit=title_volume[1] if title_volume else None,
                pack_count=pack_count,
                match=match,
                raw_payload={
                    "seed_query": seed.query,
                    "http_status": status,
                    "error": error,
                },
            )
        )
        if len(offers) >= limit:
            break
    return offers
