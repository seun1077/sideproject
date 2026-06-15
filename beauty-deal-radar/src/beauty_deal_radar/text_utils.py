from __future__ import annotations

import re


PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,8})\s*원")
VOLUME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|g|G|매)")
SPACE_RE = re.compile(r"\s+")


def clean(text: str | None) -> str:
    return SPACE_RE.sub(" ", text or "").strip()


def compact(text: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", text or "").lower()


def parse_price(text: str | None) -> int | None:
    prices: list[int] = []
    for raw in PRICE_RE.findall(text or ""):
        value = int(raw.replace(",", ""))
        if 500 <= value <= 2_000_000:
            prices.append(value)
    return min(prices) if prices else None


def parse_volume(text: str | None) -> tuple[float, str] | None:
    match = VOLUME_RE.search(text or "")
    if not match:
        return None
    unit = match.group(2).lower()
    if unit == "ml":
        unit = "ml"
    elif unit == "g":
        unit = "g"
    return float(match.group(1)), unit


def _target_volume_pattern(target_volume: tuple[float, str]) -> str:
    volume_value, volume_unit = target_volume
    volume_number = int(volume_value) if volume_value.is_integer() else volume_value
    return rf"{re.escape(str(volume_number))}\s*{re.escape(volume_unit)}"


def _sum_plus_bundle(raw: str) -> int | None:
    compacted = re.sub(r"\s+", "", raw)
    if not re.fullmatch(r"\d+(?:개|입)?(?:\+\d+(?:개|입)?){1,5}", compacted):
        return None
    counts = [int(value) for value in re.findall(r"\d+", compacted)]
    total = sum(counts)
    return total if 1 <= total <= 20 else None


def parse_pack_count(text: str | None, target_volume: tuple[float, str] | None = None) -> int:
    text = text or ""
    if target_volume:
        target_pattern = _target_volume_pattern(target_volume)
        volume_re = re.compile(target_pattern, re.IGNORECASE)
        target_occurrences = len(volume_re.findall(text))
        if 2 <= target_occurrences <= 20:
            return target_occurrences

        all_volume_matches = list(VOLUME_RE.finditer(text))
        plus_counts: list[int] = []
        for index, match in enumerate(volume_re.finditer(text)):
            next_volume_start = len(text)
            for volume_match in all_volume_matches:
                if volume_match.start() > match.end():
                    next_volume_start = volume_match.start()
                    break
            segment = text[match.end() : next_volume_start]
            plus_match = re.match(
                r"\s*([0-9]+(?:\s*(?:개|입)?\s*\+\s*[0-9]+(?:\s*(?:개|입)?)?){1,5})",
                segment,
            )
            if plus_match and (count := _sum_plus_bundle(plus_match.group(1))) is not None:
                plus_counts.append(count)
        if plus_counts:
            return max(plus_counts)

        parenthetical_bundle = re.compile(
            rf"{target_pattern}\s*[\(\[]\s*([^\)\]]*(?:본품|리필)[^\)\]]*)[\)\]]",
            re.IGNORECASE,
        )
        bundle_counts = []
        for match in parenthetical_bundle.finditer(text):
            counts = [int(value) for value in re.findall(r"(\d+)\s*(?:개|입)", match.group(1))]
            total = sum(counts)
            if 1 <= total <= 20:
                bundle_counts.append(total)
        if bundle_counts:
            return max(bundle_counts)

        parenthetical = re.compile(
            rf"{target_pattern}\s*[\(\[]?\s*(?:본품|리필)?\s*(\d+)\s*(?:개|입)\s*[\)\]]?",
            re.IGNORECASE,
        )
        parenthetical_counts = [int(match.group(1)) for match in parenthetical.finditer(text)]
        parenthetical_counts = [count for count in parenthetical_counts if 1 <= count <= 20]
        if parenthetical_counts:
            return max(parenthetical_counts)

        exact = re.compile(
            rf"{target_pattern}\s*(?:x|X|×|\*|\s)?\s*(\d+)\s*(?:개|입|set|SET|세트)?",
            re.IGNORECASE,
        )
        matched_counts = [int(match.group(1)) for match in exact.finditer(text)]
        matched_counts = [count for count in matched_counts if 1 <= count <= 20]
        if matched_counts:
            return max(matched_counts)
        if target_occurrences >= 1:
            return 1

    counts: list[int] = []
    for match in re.finditer(r"(?:x|X|×|\*)\s*(\d+)|(\d+)\s*(?:개|입|set|SET|세트)", text):
        raw = match.group(1) or match.group(2)
        if raw:
            value = int(raw)
            if 1 <= value <= 20:
                counts.append(value)
    return max(counts) if counts else 1


def canonical_key(brand: str, product: str, volume_hint: str) -> str:
    return compact(f"{brand}:{product}:{volume_hint}")
