from __future__ import annotations

import unittest

from beauty_deal_radar.collectors.algumon import _match_seed
from beauty_deal_radar.collectors.deal_match import looks_like_beauty_deal
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

    def test_beauty_terms_can_enter_source_queue_before_product_match(self) -> None:
        self.assertTrue(looks_like_beauty_deal("직잭 바이오던스 겔마스크팩 16매입 23,000원"))
        self.assertTrue(looks_like_beauty_deal("올리브영 라운드랩 선크림 1+1 특가"))
        self.assertFalse(looks_like_beauty_deal("올리브영 상품권 1만원권 8,800원"))
        self.assertFalse(looks_like_beauty_deal("아모레몰 뷰티포인트받은거"))
        self.assertFalse(looks_like_beauty_deal("생활용품 지마켓 디스크 바른요 허리 보호대 22,410원"))
        self.assertFalse(looks_like_beauty_deal("국내산 한돈 오겹살 구이용 15,630원"))


if __name__ == "__main__":
    unittest.main()
