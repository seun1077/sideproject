from __future__ import annotations

import datetime as dt
import re


DATE_RANGE_RE = re.compile(
    r"(?P<sm>\d{1,2})\s*/\s*(?P<sd>\d{1,2})\s*(?:\([^)]+\))?\s*[~\-–]\s*(?P<em>\d{1,2})\s*/\s*(?P<ed>\d{1,2})"
)
KOREAN_DATE_RANGE_RE = re.compile(
    r"(?P<sm>\d{1,2})\s*월\s*(?P<sd>\d{1,2})\s*일?\s*(?:\([^)]+\))?\s*[~\-–]\s*(?P<em>\d{1,2})\s*월\s*(?P<ed>\d{1,2})\s*일?"
)
MONTH_DAY_RE = re.compile(r"(?P<m>\d{1,2})\s*/\s*(?P<d>\d{1,2})")
KOREAN_MONTH_DAY_RE = re.compile(r"(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일?")
UNTIL_RE = re.compile(r"(?:~|까지|종료|마감)\s*(?P<m>\d{1,2})\s*/\s*(?P<d>\d{1,2})")
TIME_RE = re.compile(r"(?P<h>\d{1,2})\s*시(?:\s*(?P<mi>\d{1,2})\s*분)?")
KST = dt.timezone(dt.timedelta(hours=9))


def _iso(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S%z")


def _at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=KST)


def _roll_year(base: dt.date, month: int, day: int) -> int:
    year = base.year
    try:
        candidate = dt.date(year, month, day)
    except ValueError:
        return year
    if candidate < base - dt.timedelta(days=60):
        return year + 1
    return year


def parse_sale_period(text: str, collected_at: str | None = None) -> tuple[str | None, str | None]:
    base_dt = dt.datetime.fromisoformat((collected_at or "").replace("Z", "+00:00")).astimezone(KST) if collected_at else dt.datetime.now(KST)
    base = base_dt.date()
    text = text or ""

    range_match = DATE_RANGE_RE.search(text) or KOREAN_DATE_RANGE_RE.search(text)
    if range_match:
        start_month = int(range_match.group("sm"))
        start_day = int(range_match.group("sd"))
        end_month = int(range_match.group("em"))
        end_day = int(range_match.group("ed"))
        start_year = _roll_year(base, start_month, start_day)
        end_year = start_year if (end_month, end_day) >= (start_month, start_day) else start_year + 1
        start_at = _at(start_year, start_month, start_day)
        end_at = _at(end_year, end_month, end_day, 23, 59)
        return _iso(start_at), _iso(end_at)

    until_match = UNTIL_RE.search(text)
    if until_match:
        month = int(until_match.group("m"))
        day = int(until_match.group("d"))
        year = _roll_year(base, month, day)
        return None, _iso(_at(year, month, day, 23, 59))

    dates = MONTH_DAY_RE.findall(text) or KOREAN_MONTH_DAY_RE.findall(text)
    if dates:
        month, day = (int(value) for value in dates[-1])
        year = _roll_year(base, month, day)
        return None, _iso(_at(year, month, day, 23, 59))

    if "오늘" in text or "단 하루" in text or "일일특가" in text:
        start = dt.datetime.combine(base, dt.time(0, 0), tzinfo=KST)
        end = dt.datetime.combine(base, dt.time(23, 59), tzinfo=KST)
        return _iso(start), _iso(end)

    time_match = TIME_RE.search(text)
    if time_match:
        hour = min(23, int(time_match.group("h")))
        minute = min(59, int(time_match.group("mi") or 0))
        start = dt.datetime.combine(base, dt.time(hour, minute), tzinfo=KST)
        end = dt.datetime.combine(base, dt.time(23, 59), tzinfo=KST)
        return _iso(start), _iso(end)

    return None, None
