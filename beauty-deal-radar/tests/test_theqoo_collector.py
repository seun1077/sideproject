from __future__ import annotations

import unittest
from unittest.mock import patch

from beauty_deal_radar.collectors.theqoo import collect_theqoo_deals
from beauty_deal_radar.models import ProductSeed


SAMPLE_HTML = """
<html><body>
  <table>
    <tr>
      <td>271377</td>
      <td>생활용품</td>
      <td><a href="/theqdeal/123">지그재그)</a></td>
      <td><a href="/theqdeal/123">직잭 바이오던스 겔마스크팩 16매입 23,000원 ~6/17까지</a></td>
      <td>(23,000원)</td>
    </tr>
    <tr>
      <td>271375</td>
      <td>생활용품</td>
      <td><a href="/theqdeal/125">디스크 바른요 허리 보호대</a></td>
      <td>(22,410원)</td>
    </tr>
    <tr>
      <td>271376</td>
      <td>먹거리</td>
      <td><a href="/theqdeal/124">국내산 한돈 오겹살 구이용 (15630 무배)</a></td>
      <td>(15,630원)</td>
    </tr>
  </table>
</body></html>
"""


class TheQooCollectorTest(unittest.TestCase):
    def test_collects_beauty_deals_without_existing_product_match(self) -> None:
        seeds = [
            ProductSeed(
                brand="라운드랩",
                product="자작나무 수분 선크림",
                query="라운드랩 자작나무 선크림",
                category="선케어",
                volume_hint="50ml",
            )
        ]
        with patch("beauty_deal_radar.collectors.theqoo.fetch", return_value=(200, SAMPLE_HTML, None)):
            posts = collect_theqoo_deals(seeds)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].source_code, "theqoo")
        self.assertIn("바이오던스", posts[0].title)
        self.assertEqual(posts[0].extracted_price_krw, 23000)
        self.assertIsNone(posts[0].product_key)
        self.assertEqual(posts[0].source_category, "생활용품")
        self.assertEqual(posts[0].sale_ends_at, "2026-06-17T23:59:00+0900")


if __name__ == "__main__":
    unittest.main()
