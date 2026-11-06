import resolve


def test_exact_name_scores_point_eight():
    assert resolve.score_candidate("KFC", "KFC") == 0.80


def test_normalized_name_beats_exact():
    assert resolve.score_candidate("kfc", "K.F.C.") == 0.85


def test_accented_name_normalizes():
    # NFKD + combining-mark strip: "L'Oréal" -> "loreal", not "loral".
    assert resolve.score_candidate("Loreal", "L'Oréal") >= 0.80


def test_filter_keeps_normalized_variants():
    ads = [
        {"id": "a", "page_name": "K.F.C."},
        {"id": "b", "page_name": "KFC"},
        {"id": "c", "page_name": " kfc "},
        {"id": "d", "page_name": "Other"},
    ]
    resolution, kept = resolve.filter_ads(ads, "KFC")
    assert "error" not in resolution
    assert [ad["id"] for ad in kept] == ["a", "b", "c"]


def test_candidates_deduped_by_page():
    """Six ads from one page are one candidate, not six of the ten slots."""
    names = ["KFC Corporation"] * 6 + ["KFC Restaurant"]
    result = resolve.resolve_advertiser("KFC", names)
    assert result["error"] == "name_not_matched"
    assert len(result["candidates"]) == 2
    assert {c["page_name"] for c in result["candidates"]} == {
        "KFC Corporation",
        "KFC Restaurant",
    }


def test_below_threshold_returns_name_not_matched():
    result = resolve.resolve_advertiser(
        "Burger King", ["entel", "Soundlines Group"]
    )
    assert result["error"] == "name_not_matched"
    assert result["target"] == "Burger King"
    assert result["threshold"] == 0.80
    assert isinstance(result["candidates"], list)
    assert all(set(c) == {"page_name", "score"} for c in result["candidates"])
