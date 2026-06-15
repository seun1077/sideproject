from __future__ import annotations

import unittest

from beauty_deal_radar.collectors.algumon import _match_seed
from beauty_deal_radar.models import ProductSeed


class AlgumonCollectorTest(unittest.TestCase):
    def test_generic_words_do_not_match_unrelated_deals(self) -> None:
        seed = ProductSeed(
            brand="에스트라",
            product="아토베리어365 크림",
            query="에스트라 아토베리어365 크림",
            category="크림",
            volume_hint="80ml",
        )

        score, keywords = _match_seed("투게더 오리지널 바닐라 아이스크림", seed)

        self.assertEqual(score, 0)
        self.assertEqual(keywords, [])

    def test_brand_or_distinctive_product_tokens_can_match(self) -> None:
        seed = ProductSeed(
            brand="코스알엑스",
            product="어드밴스드 스네일 96 뮤신 에센스",
            query="코스알엑스 스네일 96 에센스",
            category="에센스",
            volume_hint="100ml",
        )

        score, keywords = _match_seed("코스알엑스 스네일 96 뮤신 에센스 특가", seed)

        self.assertGreaterEqual(score, 80)
        self.assertIn("코스알엑스", keywords)


if __name__ == "__main__":
    unittest.main()
