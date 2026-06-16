from __future__ import annotations

from .shared import now_stamp
from ..http import fetch
from ..text_utils import clean


TARGETS = [
    ("algumon", "https://www.algumon.com/robots.txt"),
    ("algumon", "https://www.algumon.com/n/deal"),
    ("danawa", "https://www.danawa.com/robots.txt"),
    ("danawa", "https://search.danawa.com/dsearch.php?query=%EC%84%A0%ED%81%AC%EB%A6%BC"),
    ("theqoo", "https://theqoo.net/robots.txt"),
    ("theqoo", "https://theqoo.net/theqdeal"),
    ("oliveyoung", "https://www.oliveyoung.co.kr/robots.txt"),
    ("musinsa", "https://www.musinsa.com/robots.txt"),
]


def probe_sources(stamp: str | None = None) -> list[dict]:
    checked_at = stamp or now_stamp()
    rows = []
    for source_code, url in TARGETS:
        status, body, error = fetch(url)
        lower = body.lower()
        rows.append(
            {
                "checked_at": checked_at,
                "source_code": source_code,
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
    return rows
