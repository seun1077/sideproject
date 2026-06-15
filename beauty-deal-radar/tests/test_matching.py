from __future__ import annotations

import unittest

from beauty_deal_radar.matching import score_offer_match
from beauty_deal_radar.models import ProductSeed
from beauty_deal_radar.text_utils import parse_pack_count, parse_volume


class TextNormalizationTest(unittest.TestCase):
    def test_pack_count_prefers_target_volume_count(self) -> None:
        title = "닥터지 그린 마일드 업 선 플러스 50ml 2개+10ml 3개"
        self.assertEqual(parse_pack_count(title, parse_volume("50ml")), 2)

    def test_pack_count_handles_x_bundle(self) -> None:
        title = "라운드 랩 자작 나무 수분 선크림 50ml x3SET"
        self.assertEqual(parse_pack_count(title, parse_volume("50ml")), 3)

    def test_pack_count_handles_one_plus_one_plus_one(self) -> None:
        title = "라운드랩 자작나무 수분 선크림 50ml 1+1+1"
        self.assertEqual(parse_pack_count(title, parse_volume("50ml")), 3)

    def test_pack_count_handles_repeated_target_volume(self) -> None:
        title = "라운드랩 자작나무 수분 선크림 50ml+50ml+50ml"
        self.assertEqual(parse_pack_count(title, parse_volume("50ml")), 3)

    def test_pack_count_does_not_count_gift_volume_bundle(self) -> None:
        title = "조선 미녀 맑은 쌀 선크림 50ml 기획 (+10ml x 2개)"
        self.assertEqual(parse_pack_count(title, parse_volume("50ml")), 1)


class MatchingTest(unittest.TestCase):
    def test_rejects_volume_mismatch(self) -> None:
        seed = ProductSeed(
            brand="바이오더마",
            product="센시비오 H2O",
            query="바이오더마 센시비오 H2O",
            category="클렌징워터",
            volume_hint="500ml",
        )
        result = score_offer_match(seed, "바이오더마 센시비오 H2O 클렌징 워터 100ml")
        self.assertEqual(result.status, "excluded")
        self.assertIn("volume_mismatch", result.exclusion_reason)

    def test_accepts_exact_product(self) -> None:
        seed = ProductSeed(
            brand="라운드랩",
            product="자작나무 수분 선크림",
            query="라운드랩 자작나무 선크림",
            category="선케어",
            volume_hint="50ml",
        )
        result = score_offer_match(seed, "라운드 랩 자작 나무 수분 선크림 50ml")
        self.assertEqual(result.status, "candidate")
        self.assertTrue(result.baseline_eligible)

    def test_rejects_product_line_variant(self) -> None:
        seed = ProductSeed(
            brand="조선미녀",
            product="맑은쌀 선크림",
            query="조선미녀 맑은쌀 선크림",
            category="선케어",
            volume_hint="50ml",
        )
        result = score_offer_match(seed, "조선 미녀 맑은 쌀 선크림 아쿠아프레쉬 50ml")
        self.assertEqual(result.status, "excluded")
        self.assertIn("variant", result.exclusion_reason)


if __name__ == "__main__":
    unittest.main()
