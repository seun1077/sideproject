from __future__ import annotations

import unittest
from unittest.mock import patch

from beauty_deal_radar.collectors.ruliweb import collect_ruliweb_deals
from beauty_deal_radar.models import ProductSeed


SAMPLE_HTML = """
<html><body>
  <table>
    <tr>
      <td>104900</td>
      <td>화장품</td>
      <td><a href="https://bbs.ruliweb.com/market/board/1020/read/104900?">
        [올리브영] 라운드랩 선크림 1+1 (6/16~6/20) 19,900원
      </a></td>
    </tr>
    <tr>
      <td>104901</td>
      <td>음식</td>
      <td><a href="https://bbs.ruliweb.com/market/board/1020/read/104901?">
        [네이버] 오뚜기밥 24개 18,900원
      </a></td>
    </tr>
  </table>
</body></html>
"""


class RuliwebCollectorTest(unittest.TestCase):
    def test_collects_cosmetic_category_with_sale_period(self) -> None:
        seeds = [
            ProductSeed(
                brand="라운드랩",
                product="자작나무 수분 선크림",
                query="라운드랩 자작나무 선크림",
                category="선케어",
                volume_hint="50ml",
            )
        ]
        with patch("beauty_deal_radar.collectors.ruliweb.fetch", return_value=(200, SAMPLE_HTML, None)):
            posts = collect_ruliweb_deals(seeds)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].source_code, "ruliweb")
        self.assertEqual(posts[0].source_category, "화장품")
        self.assertEqual(posts[0].extracted_price_krw, 19900)
        self.assertEqual(posts[0].sale_starts_at, "2026-06-16T00:00:00+0900")
        self.assertEqual(posts[0].sale_ends_at, "2026-06-20T23:59:00+0900")


if __name__ == "__main__":
    unittest.main()
