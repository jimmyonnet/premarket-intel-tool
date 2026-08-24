from scripts.fetch_indices import ASIA_QUOTE_PAGES, parse_asia_quote_page


NIKKEI_QUOTE_TEXT = """Nikkei 225
^N225
加入自選股
66,079.35
JPY
62.99
(0.10%)
開盤中 | 2026/08/24 09:51 台北時間 (股價延遲 20 分鐘)
"""

KOSPI_QUOTE_TEXT = """KOSPI Composite Index
^KS11
加入自選股
6,792.09
KRW
120.86
(1.75%)
開盤中 | 2026/08/24 09:46 台北時間 (股價延遲 20 分鐘)
"""


def test_parse_nikkei_from_user_specified_yahoo_quote_page():
    quote = parse_asia_quote_page(NIKKEI_QUOTE_TEXT, ASIA_QUOTE_PAGES["nikkei225"])

    assert quote["name"] == "日經225指數"
    assert quote["value"] == 66079.35
    assert quote["change_pct"] == 0.10
    assert quote["updated_cst"] == "08/24 09:51"
    assert quote["source_url"] == "https://tw.stock.yahoo.com/quote/%5EN225"


def test_parse_kospi_from_user_specified_yahoo_quote_page():
    quote = parse_asia_quote_page(KOSPI_QUOTE_TEXT, ASIA_QUOTE_PAGES["kospi"])

    assert quote["name"] == "韓國綜合指數"
    assert quote["value"] == 6792.09
    assert quote["updated_cst"] == "08/24 09:46"
    assert quote["source_url"] == "https://tw.stock.yahoo.com/quote/%5EKS11"


def test_parse_asia_quote_page_returns_none_for_incomplete_response():
    assert parse_asia_quote_page("^N225\n資料載入中", ASIA_QUOTE_PAGES["nikkei225"]) is None
