from __future__ import annotations

from ..models import ProductSeed


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

BEAUTY_DEAL_TOKENS = {
    "기초",
    "마스크팩",
    "선크림",
    "선스틱",
    "선케어",
    "토너",
    "앰플",
    "세럼",
    "에센스",
    "패드",
    "수분크림",
    "크림",
    "클렌징",
    "폼클렌징",
    "오일",
    "립밤",
    "쿠션",
    "화장품",
    "뷰티",
    "이니스프리",
    "에뛰드",
    "라운드랩",
    "닥터지",
    "토리든",
    "아누아",
    "메디힐",
    "바이오던스",
}

EXCLUDED_SOURCE_DEAL_TOKENS = {
    "상품권",
    "기프트카드",
    "네이버페이",
    "포인트",
    "적립",
}


def tokens(value: str) -> set[str]:
    return {
        token.strip()
        for token in value.split()
        if len(token.strip()) >= 2 and token.strip() not in GENERIC_MATCH_TOKENS
    }


def match_seed(title: str, seed: ProductSeed) -> tuple[int, list[str]]:
    brand_tokens = tokens(seed.brand)
    product_tokens = tokens(seed.product) | tokens(seed.query)
    matched_brand = sorted(token for token in brand_tokens if token in title)
    matched_product = sorted(token for token in product_tokens if token in title)
    if not matched_brand and len(matched_product) < 2:
        return 0, []
    score = min(100, len(matched_brand) * 55 + len(matched_product) * 18)
    return score, [*matched_brand, *matched_product]


def best_seed_match(title: str, seeds: list[ProductSeed]) -> tuple[ProductSeed | None, int, list[str]]:
    matches = [(seed, *match_seed(title, seed)) for seed in seeds]
    matches = [(seed, score, keywords) for seed, score, keywords in matches if score > 0]
    if not matches:
        return None, 0, []
    return max(matches, key=lambda row: row[1])


def looks_like_beauty_deal(text: str) -> bool:
    if any(token in text for token in EXCLUDED_SOURCE_DEAL_TOKENS):
        return False
    return any(token in text for token in BEAUTY_DEAL_TOKENS)
