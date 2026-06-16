from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductSeed:
    brand: str
    product: str
    query: str
    category: str
    volume_hint: str


@dataclass(frozen=True)
class MatchResult:
    score: int
    status: str
    exclusion_reason: str
    baseline_eligible: bool


@dataclass(frozen=True)
class OfferCandidate:
    source_code: str
    product_key: str
    title: str
    url: str
    package_price_krw: int | None
    normalized_price_krw: int | None
    volume_value: float | None
    volume_unit: str | None
    pack_count: int
    match: MatchResult
    raw_payload: dict


@dataclass(frozen=True)
class DealPostCandidate:
    source_code: str
    product_key: str | None
    title: str
    url: str
    extracted_price_krw: int | None
    matched_keywords: str
    match_score: int
    raw_payload: dict
    source_category: str | None = None
    sale_starts_at: str | None = None
    sale_ends_at: str | None = None
