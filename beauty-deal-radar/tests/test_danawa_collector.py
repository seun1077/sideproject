from __future__ import annotations

import unittest

from beauty_deal_radar.collectors.danawa import parse_danawa_detail_page


class DanawaCollectorTest(unittest.TestCase):
    def test_parse_detail_page_uses_real_title_and_lowest_price(self) -> None:
        body = """
        <html>
          <head>
            <title>메디힐 마데카소사이드 흔적 패드 100매 (본품2개) : 다나와 가격비교</title>
            <meta name="Title" content="[다나와] 메디힐 마데카소사이드 흔적 패드 100매 (본품2개)" />
            <meta property="og:description" content="최저가 27,130원" />
          </head>
        </html>
        """

        title, price = parse_danawa_detail_page(body)

        self.assertEqual(title, "메디힐 마데카소사이드 흔적 패드 100매 (본품2개)")
        self.assertEqual(price, 27130)


if __name__ == "__main__":
    unittest.main()
