from scripts.review import build_review


def test_build_review_calculates_signal_stats():
    output = build_review(
        {"今日出關": [{"code": "2330", "name": "台積電", "close": 100}, {"code": "2454", "name": "聯發科", "close": 100}]},
        {"2330": {"close": 102, "high": 105}, "2454": {"close": 98, "high": 103}},
    )
    assert len(output["detail"]) == 2
    assert output["stats"]["今日出關"] == {"n": 2, "win_rate": 50.0, "avg_ret": 0.0, "avg_high": 4.0}
