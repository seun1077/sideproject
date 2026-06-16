from __future__ import annotations

import unittest

from beauty_deal_radar.deal_period import parse_sale_period


class DealPeriodTest(unittest.TestCase):
    def test_month_day_uses_current_korean_year(self) -> None:
        start, end = parse_sale_period("라방 특가 ~6/17 8:59까지", "2026-06-16T00:00:00Z")

        self.assertIsNone(start)
        self.assertEqual(end, "2026-06-17T23:59:00+0900")

    def test_date_range_uses_current_korean_year(self) -> None:
        start, end = parse_sale_period("바캉스 준비 세일 (6/15~6/20)", "2026-06-16T00:00:00Z")

        self.assertEqual(start, "2026-06-15T00:00:00+0900")
        self.assertEqual(end, "2026-06-20T23:59:00+0900")

    def test_korean_month_day_range(self) -> None:
        start, end = parse_sale_period("바캉스 준비 세일 (6월15일(월)~6월20일(토))", "2026-06-16T00:00:00Z")

        self.assertEqual(start, "2026-06-15T00:00:00+0900")
        self.assertEqual(end, "2026-06-20T23:59:00+0900")

    def test_today_uses_collected_korean_date(self) -> None:
        start, end = parse_sale_period("오늘 단 하루 특가", "2026-06-15T23:30:00Z")

        self.assertEqual(start, "2026-06-16T00:00:00+0900")
        self.assertEqual(end, "2026-06-16T23:59:00+0900")


if __name__ == "__main__":
    unittest.main()
