import resolve


def test_exact_name_scores_point_eight():
    assert resolve.score_candidate("KFC", "KFC") == 0.80


def test_normalized_name_beats_exact():
    assert resolve.score_candidate("kfc", "K.F.C.") == 0.85


def test_below_threshold_returns_name_not_matched():
    result = resolve.resolve_advertiser(
        "Burger King", ["entel", "Soundlines Group"]
    )
    assert result["error"] == "name_not_matched"
    assert result["target"] == "Burger King"
    assert result["threshold"] == 0.80
    assert isinstance(result["candidates"], list)
    assert all(set(c) == {"page_name", "score"} for c in result["candidates"])
