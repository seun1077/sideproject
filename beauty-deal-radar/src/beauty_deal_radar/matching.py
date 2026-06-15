from __future__ import annotations

import re

from .models import MatchResult, ProductSeed
from .text_utils import clean, compact, parse_volume


CATEGORY_TERMS = {
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


def score_offer_match(seed: ProductSeed, title: str) -> MatchResult:
    title_clean = clean(title)
    title_compact = compact(title_clean)
    brand_compact = compact(seed.brand)
    query_tokens = [token for token in re.split(r"\s+", seed.query) if len(token) >= 2]

    score = 0
    reasons: list[str] = []
    excludes: list[str] = []

    if brand_compact and brand_compact in title_compact:
        score += 30
    else:
        reasons.append("brand_missing")

    matched_tokens = [token for token in query_tokens if compact(token) in title_compact]
    score += min(40, len(matched_tokens) * 10)

    seed_volume = parse_volume(seed.volume_hint)
    title_volume = parse_volume(title_clean)
    if seed_volume:
        if compact(seed.volume_hint) in title_compact:
            score += 20
        if title_volume and seed_volume[1] == title_volume[1]:
            if abs(seed_volume[0] - title_volume[0]) > 0.01:
                excludes.append("volume_mismatch")

    if "중고" in title_clean:
        excludes.append("used")
    if "마스크" in title_clean or "팩" in title_clean:
        if "마스크" not in seed.product and "팩" not in seed.product:
            excludes.append("mask_or_pack_variant")
    if "선스틱" in title_clean and "선스틱" not in seed.product:
        excludes.append("sunstick_variant")

    required = CATEGORY_TERMS.get(seed.category, [])
    if required and not any(compact(term) in title_compact for term in required):
        excludes.append("category_term_missing")

    if excludes:
        return MatchResult(score=score, status="excluded", exclusion_reason=",".join(excludes), baseline_eligible=False)
    if score >= 50:
        return MatchResult(score=score, status="candidate", exclusion_reason="", baseline_eligible=True)
    return MatchResult(score=score, status="rejected", exclusion_reason=",".join(reasons), baseline_eligible=False)

