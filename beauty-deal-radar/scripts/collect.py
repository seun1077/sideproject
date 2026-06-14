from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
SEEDS = DATA / "seeds.csv"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 BeautyDealRadarResearch/0.1"
)

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,8})\s*원")
VOLUME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|g|G|매)")
PACK_RE = re.compile(r"(?:x|X|×|\*)\s*(\d+)|(\d+)\s*(?:개|입|set|SET|세트)")
SPACE_RE = re.compile(r"\s+")


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch(url: str, timeout: int = 20) -> tuple[int | None, str, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            charset = res.headers.get_content_charset() or "utf-8"
            body = res.read().decode(charset, errors="replace")
            return res.status, body, None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, f"HTTP {exc.code}"
    except Exception as exc:  # keep the probe resilient
        return None, "", type(exc).__name__ + ": " + str(exc)


def clean(text: str) -> str:
    return SPACE_RE.sub(" ", text or "").strip()


def compact(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", text or "").lower()


def score_match(seed: dict[str, str], title: str) -> tuple[int, str, bool]:
    title_clean = clean(title)
    title_compact = compact(title_clean)
    product_compact = compact(seed["product"])
    brand_compact = compact(seed["brand"])
    query_tokens = [token for token in re.split(r"\s+", seed["query"]) if len(token) >= 2]

    score = 0
    reasons = []
    if brand_compact and brand_compact in title_compact:
        score += 30
    else:
        reasons.append("brand_missing")

    matched_tokens = [token for token in query_tokens if compact(token) in title_compact]
    score += min(40, len(matched_tokens) * 10)

    volume = compact(seed.get("volume_hint", ""))
    if volume and volume in title_compact:
        score += 20

    category = seed.get("category", "")
    excludes = []
    if "중고" in title_clean:
        excludes.append("used")
    if "마스크" in title_clean or "팩" in title_clean:
        if "마스크" not in seed["product"] and "팩" not in seed["product"]:
            excludes.append("mask_or_pack_variant")
    if "선스틱" in title_clean and "선스틱" not in seed["product"]:
        excludes.append("sunstick_variant")

    seed_volume = parse_volume(seed.get("volume_hint", ""))
    title_volume = parse_volume(title_clean)
    if seed_volume and title_volume and seed_volume[1] == title_volume[1]:
        if abs(seed_volume[0] - title_volume[0]) > 0.01:
            excludes.append("volume_mismatch")

    category_terms = {
        "토너": ["토너"],
        "세럼": ["세럼"],
        "앰플": ["앰플"],
        "에센스": ["에센스"],
        "크림": ["크림"],
        "패드": ["패드"],
        "클렌징": ["오일", "클렌징"],
        "클렌징워터": ["클렌징", "워터", "h2o"],
        "선케어": ["선크림", "선에센스", "선플러스", "안뗄리오스"],
    }
    required = category_terms.get(category, [])
    if required and not any(compact(term) in title_compact for term in required):
        excludes.append("category_term_missing")

    usable = score >= 50 and not excludes
    reason = ",".join(excludes or reasons)
    return score, reason, usable


def parse_volume(text: str) -> tuple[float, str] | None:
    match = VOLUME_RE.search(text or "")
    if not match:
        return None
    unit = match.group(2).lower()
    if unit == "ml":
        unit = "ml"
    if unit == "g":
        unit = "g"
    return float(match.group(1)), unit


def parse_pack_count(text: str) -> int:
    counts = []
    for match in PACK_RE.finditer(text or ""):
        raw = match.group(1) or match.group(2)
        if raw:
            value = int(raw)
            if 1 <= value <= 20:
                counts.append(value)
    return max(counts) if counts else 1


def parse_price(text: str) -> int | None:
    matches = PRICE_RE.findall(text)
    prices: list[int] = []
    for raw in matches:
        value = int(raw.replace(",", ""))
        if 500 <= value <= 2_000_000:
            prices.append(value)
    return min(prices) if prices else None


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


def read_seeds() -> list[dict[str, str]]:
    with SEEDS.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def probe_sources(stamp: str) -> list[dict]:
    targets = [
        ("algumon_robots", "https://www.algumon.com/robots.txt"),
        ("algumon_latest", "https://www.algumon.com/n/deal"),
        ("danawa_robots", "https://www.danawa.com/robots.txt"),
        ("danawa_search", "https://search.danawa.com/dsearch.php?query=%EC%84%A0%ED%81%AC%EB%A6%BC"),
        ("oliveyoung_robots", "https://www.oliveyoung.co.kr/robots.txt"),
        ("musinsa_robots", "https://www.musinsa.com/robots.txt"),
    ]
    rows = []
    for name, url in targets:
        status, body, error = fetch(url)
        lower = body.lower()
        rows.append(
            {
                "checked_at": stamp,
                "source": name,
                "url": url,
                "status": status,
                "bytes": len(body.encode("utf-8")),
                "error": error or "",
                "looks_blocked": bool(
                    "cloudflare" in lower
                    or "enable javascript and cookies" in lower
                    or "잠시만 기다려 주세요" in body
                ),
                "snippet": clean(body[:220]),
            }
        )
        time.sleep(0.4)
    return rows


def collect_danawa_for_seed(seed: dict[str, str], stamp: str, limit: int = 8) -> list[dict]:
    query = seed["query"]
    url = "https://search.danawa.com/dsearch.php?" + urllib.parse.urlencode({"query": query})
    status, body, error = fetch(url)
    if status != 200 or not body:
        return [
            {
                "collected_at": stamp,
                "source": "danawa",
                "seed_query": query,
                "brand": seed["brand"],
                "seed_product": seed["product"],
                "status": status,
                "error": error or "empty body",
            }
        ]

    (RAW / "danawa").mkdir(parents=True, exist_ok=True)
    safe_query = re.sub(r"[^0-9A-Za-z가-힣]+", "_", query).strip("_")
    (RAW / "danawa" / f"{stamp}_{safe_query}.html").write_text(body, encoding="utf-8")

    doc = html.fromstring(body)
    items = doc.xpath(
        "//li[contains(@class, 'prod_item') or contains(@class, 'product_list_item')]"
    )
    if not items:
        items = doc.xpath("//div[contains(@class, 'prod_main_info')]/ancestor::li[1]")

    rows = []
    seen = set()
    for item in items:
        title_nodes = item.xpath(
            ".//*[contains(@class, 'prod_name')]//a/text() | "
            ".//*[contains(@class, 'prod_name')]//text() | "
            ".//a[contains(@class, 'click_log_product_standard_title_')]/text()"
        )
        title = clean(" ".join(title_nodes))
        if not title:
            continue
        text = clean(" ".join(item.xpath(".//text()")))
        price = parse_danawa_item_price(item)
        links = item.xpath(".//*[contains(@class, 'prod_name')]//a/@href | .//a/@href")
        link = links[0] if links else url
        key = (title, price, link)
        if key in seen:
            continue
        seen.add(key)
        match_score, excluded_reason, usable = score_match(seed, title)
        pack_count = parse_pack_count(title)
        normalized_price = round(price / pack_count) if price and pack_count else price
        title_volume = parse_volume(title)
        rows.append(
            {
                "collected_at": stamp,
                "source": "danawa",
                "seed_query": query,
                "brand": seed["brand"],
                "seed_product": seed["product"],
                "category": seed["category"],
                "volume_hint": seed["volume_hint"],
                "result_title": title,
                "price_krw": price,
                "normalized_price_krw": normalized_price,
                "pack_count": pack_count,
                "parsed_volume_value": title_volume[0] if title_volume else "",
                "parsed_volume_unit": title_volume[1] if title_volume else "",
                "match_score": match_score,
                "excluded_reason": excluded_reason,
                "usable_for_baseline": usable,
                "url": link,
                "status": status,
                "error": "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def collect_algumon_latest(seeds: list[dict[str, str]], stamp: str) -> list[dict]:
    url = "https://www.algumon.com/n/deal"
    status, body, error = fetch(url)
    if status != 200 or not body:
        return [
            {
                "collected_at": stamp,
                "source": "algumon",
                "status": status,
                "error": error or "empty body",
            }
        ]

    (RAW / "algumon_latest.html").write_text(body, encoding="utf-8")
    doc = html.fromstring(body)
    anchors = doc.xpath("//a[@href]")
    keywords = []
    for seed in seeds:
        parts = [seed["brand"], seed["product"], seed["query"], seed["category"]]
        for part in parts:
            for token in re.split(r"\s+", part):
                token = token.strip()
                if len(token) >= 2:
                    keywords.append(token)
    keywords = sorted(set(keywords), key=len, reverse=True)

    rows = []
    seen = set()
    for a in anchors:
        text = clean(" ".join(a.xpath(".//text()")))
        href = a.get("href")
        if not text or not href:
            continue
        matched = [kw for kw in keywords if kw in text]
        if not matched:
            continue
        if href.startswith("/"):
            href = urllib.parse.urljoin("https://www.algumon.com", href)
        price = parse_price(text)
        key = (text, href)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "collected_at": stamp,
                "source": "algumon",
                "result_title": text[:240],
                "price_krw": price,
                "matched_keywords": ",".join(matched[:8]),
                "url": href,
                "status": status,
                "error": "",
            }
        )
    return rows


def summarize_prices(danawa_rows: list[dict], stamp: str) -> tuple[list[dict], list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in danawa_rows:
        price = row.get("normalized_price_krw")
        if isinstance(price, int) and row.get("usable_for_baseline"):
            grouped.setdefault(row["seed_query"], []).append(row)

    snapshots = []
    candidates = []
    for seed_query, rows in grouped.items():
        prices = sorted(row["normalized_price_krw"] for row in rows)
        if not prices:
            continue
        median_price = int(statistics.median(prices))
        min_price = min(prices)
        best = next(row for row in rows if row["normalized_price_krw"] == min_price)
        discount = None
        if median_price > 0:
            discount = round((median_price - min_price) / median_price * 100, 1)
        score = 50
        if discount is not None:
            score = max(0, min(100, 50 + math.floor(discount * 2)))
        snapshot = {
            "snapshot_at": stamp,
            "seed_query": seed_query,
            "brand": best.get("brand", ""),
            "seed_product": best.get("seed_product", ""),
            "category": best.get("category", ""),
            "volume_hint": best.get("volume_hint", ""),
            "result_count": len(prices),
            "current_min_price": min_price,
            "best_package_price": best.get("price_krw"),
            "best_pack_count": best.get("pack_count", 1),
            "market_median_price": median_price,
            "discount_vs_median_pct": discount,
            "deal_score_proxy": score,
            "best_title": best.get("result_title", ""),
            "best_url": best.get("url", ""),
            "baseline_note": "current Danawa matched-result median normalized to one seed-size item; not historical",
        }
        snapshots.append(snapshot)
        if discount is not None and discount >= 15:
            candidates.append(snapshot)

    snapshots.sort(key=lambda r: (r["discount_vs_median_pct"] or 0), reverse=True)
    candidates.sort(key=lambda r: (r["deal_score_proxy"], r["discount_vs_median_pct"] or 0), reverse=True)
    return snapshots, candidates


def main() -> None:
    stamp = now_stamp()
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    seeds = read_seeds()

    source_rows = probe_sources(stamp)
    write_csv(PROCESSED / f"source_access_{stamp}.csv", source_rows)

    danawa_rows: list[dict] = []
    for seed in seeds:
        danawa_rows.extend(collect_danawa_for_seed(seed, stamp))
        time.sleep(0.7)
    write_csv(PROCESSED / f"danawa_results_{stamp}.csv", danawa_rows)

    algumon_rows = collect_algumon_latest(seeds, stamp)
    write_csv(PROCESSED / f"algumon_latest_matches_{stamp}.csv", algumon_rows)

    snapshots, candidates = summarize_prices(danawa_rows, stamp)
    write_csv(PROCESSED / f"price_snapshot_{stamp}.csv", snapshots)
    write_csv(PROCESSED / f"deal_candidates_{stamp}.csv", candidates)

    summary = {
        "snapshot_at": stamp,
        "seed_count": len(seeds),
        "danawa_rows": len([r for r in danawa_rows if r.get("price_krw")]),
        "algumon_matches": len(algumon_rows),
        "price_snapshots": len(snapshots),
        "deal_candidates_discount_ge_15pct": len(candidates),
        "outputs": {
            "source_access": str(PROCESSED / f"source_access_{stamp}.csv"),
            "danawa_results": str(PROCESSED / f"danawa_results_{stamp}.csv"),
            "algumon_matches": str(PROCESSED / f"algumon_latest_matches_{stamp}.csv"),
            "price_snapshot": str(PROCESSED / f"price_snapshot_{stamp}.csv"),
            "deal_candidates": str(PROCESSED / f"deal_candidates_{stamp}.csv"),
        },
    }
    (PROCESSED / f"summary_{stamp}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
