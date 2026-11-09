import json
from pathlib import Path

import pytest

import resolve

LIVE_MATRIX = Path(__file__).resolve().parents[1] / "evals" / "live-matrix"

# Pinned snapshots of the keyword-search listings recorded at commit a52be83.
# Kept here on purpose: evals/live-matrix is refreshed by replaying live queries,
# so its contents are mutable. These unit tests assert resolver behaviour, not
# whatever a later harvest happens to return.
RECORDED_BK_EG_PAGE_NAMES = [
    # evals/live-matrix/burger-king-eg/ads.json -> "search", a52be83
    "Ns-zlin-0125",
    "BUFFALO BURGER",
    "Burger King Malaysia",
    "DoorDash",
    "Cholesterol Relief Community",
    "BlazeReel Drama",
    "Tatiana Salazar",
    "Ns-YXB-ST2dd",
    "Talabat",
    "Xc-twoseven-One",
    "NS-Zs-02",
    "Ns-st-zsuse",
    "LumaWorld",
    "비밀의 저택에서",
    "Shortdrama-zlin-06",
    "Burger King Arabia",
]

RECORDED_BK_AE_PAGE_NAMES = [
    # evals/live-matrix/burger-king-ae/ads.json -> "advertiser_search"
    # ("search" was empty at a52be83: the pair failed upstream)
    "Burger King Arabia",
]


def _live_page_names(folder, field, fallback=None):
    """Page names from the live-matrix recording, or skip if unavailable.

    The matrix is regenerated against the live ad library, so a missing or
    empty recording means "no data to check", never a resolver failure. The
    paired ``advertiser_search`` leg is the fallback: at a52be83 the AE
    keyword-search leg failed upstream and recorded ``search: []`` while
    ``advertiser_search`` still held the page, so reading only ``search``
    skipped a recording that had data.
    """
    path = LIVE_MATRIX / folder / "ads.json"
    if not path.is_file():
        pytest.skip(f"live-matrix recording missing: {path}")
    data = json.loads(path.read_text())
    for name in (field, fallback):
        if not name:
            continue
        rows = data.get(name)
        # A non-list (legacy/partial recording) is "no data", not a crash.
        if not isinstance(rows, list):
            continue
        names = []
        for ad in rows:
            page = ad.get("page_name") if isinstance(ad, dict) else None
            if page and page not in names:
                names.append(page)
        if names:
            return names
    pytest.skip(f"live-matrix recording empty: {path} ({field})")


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


def test_country_suffix_scores_as_exact_match():
    """A country-qualified page is still the same advertiser.

    Live QSR sweep 2026-11-08: `Burger King Arabia` scored 0.60 (substring)
    and was rejected at the 0.80 threshold, taking 10/25 pairs down with it.
    """
    assert resolve.score_candidate("Burger King", "Burger King Arabia") >= 0.80
    assert resolve.score_candidate("Pizza Hut", "Pizza Hut KSA") >= 0.80
    assert resolve.score_candidate("Burger King", "Burger King UK") >= 0.80
    assert resolve.score_candidate("Burger King", "Burger King Malaysia") >= 0.80
    assert resolve.score_candidate("Domino's Pizza", "Domino's Pizza India") >= 0.80


def test_country_suffix_resolves_through_resolve_advertiser():
    result = resolve.resolve_advertiser("Burger King", ["Burger King Arabia"])
    assert "error" not in result
    assert result["page_name"] == "Burger King Arabia"

    result = resolve.resolve_advertiser("Pizza Hut", ["Pizza Hut KSA"])
    assert "error" not in result
    assert result["page_name"] == "Pizza Hut KSA"


def test_country_suffix_does_not_weaken_substring_rung():
    """Stripping is trailing-only: a brand buried mid-name stays a 0.60 miss."""
    assert resolve.score_candidate(
        "Burger King", "Manila Polyclinic - Al Rigga Burger King"
    ) == 0.60
    assert resolve.score_candidate("Burger King", "Burger King Arabia Grill") == 0.60


def test_recorded_burger_king_eg_fails_truthfully():
    """Live bug: `burger-king-eg` resolved to `Burger King Malaysia`.

    The pinned a52be83 listing (see ``RECORDED_BK_EG_PAGE_NAMES``) never
    contained a bare ``Burger King`` page, so there is nothing correct to
    pick. Asking for EG must FAIL truthfully rather than resolve the
    Malaysian page (the false PASS this test used to codify). Both
    country-qualified pages in the listing are ineligible for EG, so both
    are reported as diagnostics.
    """
    result = resolve.resolve_advertiser(
        "Burger King", RECORDED_BK_EG_PAGE_NAMES, market="EG"
    )
    assert result["error"] == "name_not_matched"
    assert result["target"] == "Burger King"
    assert result["threshold"] == 0.80
    assert "page_name" not in result
    assert [c["page_name"] for c in result["candidates"]] == [
        "Burger King Malaysia",
        "Burger King Arabia",
    ]
    assert all(c["score"] == 0.80 for c in result["candidates"])


def test_veto_only_fires_on_explicit_other_market():
    """Bare/global pages still resolve; a matching qualifier resolves."""
    # No qualifier: nothing contradicts the request.
    result = resolve.resolve_advertiser("KFC", ["KFC"], market="EG")
    assert result == {"page_name": "KFC", "score": 0.80}

    # Qualifier matches the request.
    result = resolve.resolve_advertiser(
        "Burger King", ["Burger King Egypt"], market="EG"
    )
    assert result == {"page_name": "Burger King Egypt", "score": 0.80}

    # Caller does not know the market: old behaviour, no veto.
    result = resolve.resolve_advertiser("Burger King", ["Burger King Malaysia"])
    assert result == {"page_name": "Burger King Malaysia", "score": 0.80}


def test_prefers_market_qualified_page_when_no_bare_page_exists():
    """Among country-qualified variants, the requested market wins."""
    names = ["Burger King Malaysia", "Burger King Egypt"]
    result = resolve.resolve_advertiser("Burger King", names, market="EG")
    assert result == {"page_name": "Burger King Egypt", "score": 0.80}


def test_cross_market_candidates_are_all_ineligible_not_ambiguous():
    """With a market requested, pages naming other markets are simply out.

    Malaysian and Indian pages cannot satisfy an EG query, so there is nothing
    to disambiguate: both are reported as diagnostics and neither is offered
    as a pickable tie.
    """
    names = ["Burger King Malaysia", "Burger King India"]
    result = resolve.resolve_advertiser("Burger King", names, market="EG")
    assert result["error"] == "name_not_matched"
    assert "ambiguous" not in result
    assert result["threshold"] == 0.80
    assert [c["page_name"] for c in result["candidates"]] == [
        "Burger King Malaysia",
        "Burger King India",
    ]
    assert all(c["score"] == 0.80 for c in result["candidates"])


def test_ambiguous_tie_without_requested_market_is_not_resolved_silently():
    names = ["Pizza Hut UAE", "Pizza Hut KSA"]
    result = resolve.resolve_advertiser("Pizza Hut", names)
    assert result["error"] == "name_not_matched"
    assert result["ambiguous"] is True


def test_ambiguous_candidates_are_only_the_tied_set():
    """A 0.60 runner-up is not an equally plausible page."""
    names = ["Burger King UAE", "Burger King KSA"] + [
        f"Burger King Region {i}" for i in range(10)
    ]
    result = resolve.resolve_advertiser("Burger King", names)
    assert result["error"] == "name_not_matched"
    assert result["ambiguous"] is True
    assert [c["page_name"] for c in result["candidates"]] == [
        "Burger King UAE",
        "Burger King KSA",
    ]
    assert all(c["score"] == 0.80 for c in result["candidates"])


def test_single_candidate_naming_another_market_is_rejected():
    """Market is not just a ranking hint: it vetoes a known contradiction.

    A lone ``Burger King Malaysia`` page must not be handed back for an EG
    query — that was the false PASS the live matrix recorded as true.
    """
    result = resolve.resolve_advertiser(
        "Burger King", ["Burger King Malaysia"], market="EG"
    )
    assert result["error"] == "name_not_matched"
    assert result["target"] == "Burger King"
    assert result["candidates"] == [
        {"page_name": "Burger King Malaysia", "score": 0.80}
    ]


def test_market_match_outranks_bare_page():
    """A market-scoped query prefers the qualifier that matches it."""
    result = resolve.resolve_advertiser(
        "Burger King",
        ["Burger King", "Burger King Saudi Arabia"],
        market="SA",
    )
    assert result == {"page_name": "Burger King Saudi Arabia", "score": 0.80}


def test_exactness_still_decides_when_market_is_absent():
    result = resolve.resolve_advertiser(
        "Burger King", ["Burger King Malaysia", "Burger King"]
    )
    assert result == {"page_name": "Burger King", "score": 0.80}


def test_market_tie_break_flows_through_filter_ads():
    ads = [
        {"id": "my", "page_name": "Burger King Malaysia"},
        {"id": "eg", "page_name": "Burger King Egypt"},
    ]
    resolution, kept = resolve.filter_ads(ads, "Burger King", market="EG")
    assert "error" not in resolution
    assert resolution["page_name"] == "Burger King Egypt"
    assert [ad["id"] for ad in kept] == ["eg"]


def test_recorded_burger_king_ae_resolves_arabia():
    """Recorded PASS pair `burger-king-ae` must survive the market veto.

    "Arabia" is a Gulf-regional qualifier, not a Saudi-only one: mapping it
    to SA alone vetoed the correct AE page and broke the recorded PASS.
    """
    result = resolve.resolve_advertiser(
        "Burger King", RECORDED_BK_AE_PAGE_NAMES, market="AE"
    )
    assert "error" not in result
    assert result["page_name"] == "Burger King Arabia"


def test_recorded_burger_king_eg_live_matrix_if_present():
    """Smoke the live-matrix recording without asserting its exact contents.

    The matrix is regenerated from live queries; if the EG listing has since
    gained an Egypt-compatible page, a miss is no longer the expected outcome.
    Only the invariant is checked here: with no eligible page the resolver has
    to fail truthfully, and no cross-market page may be resolved.
    """
    names = _live_page_names("burger-king-eg", "search")
    eligible = [
        name
        for name in names
        if "error" not in resolve.resolve_advertiser(
            "Burger King", [name], market="EG"
        )
    ]
    if eligible:
        pytest.skip(f"live recording now has EG-eligible pages: {eligible}")

    result = resolve.resolve_advertiser("Burger King", names, market="EG")
    assert result["error"] == "name_not_matched"
    assert "page_name" not in result


def test_recorded_burger_king_ae_live_matrix_if_present():
    """Smoke the live AE recording when it exists; skip on upstream failure.

    The AE keyword-search leg recorded empty upstream, so fall back to the
    ``advertiser_search`` leg rather than skipping a recording that has data.
    """
    names = _live_page_names(
        "burger-king-ae", "search", fallback="advertiser_search"
    )
    if "Burger King Arabia" not in names:
        pytest.skip("live recording no longer contains 'Burger King Arabia'")

    result = resolve.resolve_advertiser("Burger King", names, market="AE")
    assert result.get("page_name") == "Burger King Arabia"


def test_arabia_is_compatible_with_gulf_markets():
    """`Arabia` qualifies the Gulf, so every GCC market accepts that page.

    Trade-off documented here: the set includes SA, so a page named
    `Burger King Arabia` also resolves for a Saudi query. That is the
    price of treating "Arabia" as regional instead of Saudi-exclusive.
    """
    for market in ("AE", "SA", "BH", "KW", "OM", "QA"):
        result = resolve.resolve_advertiser(
            "Burger King", ["Burger King Arabia"], market=market
        )
        assert result == {"page_name": "Burger King Arabia", "score": 0.80}

    # Outside the Gulf it is still an explicit contradiction.
    result = resolve.resolve_advertiser(
        "Burger King", ["Burger King Arabia"], market="EG"
    )
    assert result["error"] == "name_not_matched"


def test_specific_qualifier_beats_regional_one():
    """`Saudi Arabia` names SA, not the whole Gulf the token `Arabia` spans."""
    result = resolve.resolve_advertiser(
        "Burger King", ["Burger King Saudi Arabia"], market="AE"
    )
    assert result["error"] == "name_not_matched"

    result = resolve.resolve_advertiser(
        "Burger King", ["Burger King Saudi Arabia"], market="SA"
    )
    assert result == {"page_name": "Burger King Saudi Arabia", "score": 0.80}


def test_contradicting_candidates_are_filtered_before_selection():
    """A wrong-market candidate must not shadow a correct one.

    Score dominates rank and the veto only inspected the top candidate, so
    `K.F.C. Malaysia` (0.85) shadowed `KFC Egypt` (0.80) and the EG query
    failed despite the correct page being present.
    """
    result = resolve.resolve_advertiser(
        "KFC", ["K.F.C. Malaysia", "KFC Egypt"], market="EG"
    )
    assert result == {"page_name": "KFC Egypt", "score": 0.80}


def test_all_candidates_contradicting_market_fail_with_diagnostics():
    """Filtering leaves nothing eligible: a truthful FAIL keeps the evidence."""
    result = resolve.resolve_advertiser(
        "KFC", ["K.F.C. Malaysia", "KFC India"], market="EG"
    )
    assert result["error"] == "name_not_matched"
    assert result["target"] == "KFC"
    assert {c["page_name"] for c in result["candidates"]} == {
        "K.F.C. Malaysia",
        "KFC India",
    }


def test_bare_page_survives_market_filter():
    """No qualifier means global: a bare page is always eligible."""
    result = resolve.resolve_advertiser(
        "KFC", ["KFC", "K.F.C. Malaysia"], market="EG"
    )
    assert result == {"page_name": "KFC", "score": 0.80}


def test_below_threshold_returns_name_not_matched():
    result = resolve.resolve_advertiser(
        "Burger King", ["entel", "Soundlines Group"]
    )
    assert result["error"] == "name_not_matched"
    assert result["target"] == "Burger King"
    assert result["threshold"] == 0.80
    assert isinstance(result["candidates"], list)
    assert all(set(c) == {"page_name", "score"} for c in result["candidates"])


def test_every_strippable_country_token_names_a_market():
    """A token peeled from a page name must be explainable as a market.

    ``_COUNTRY_TOKENS`` drives stripping (which decides what counts as a
    country qualifier); ``_MARKET_BY_TOKEN`` / ``_REGIONAL_MARKET_TOKENS``
    drive the market veto. A token in the first set with no entry in either
    mapping would strip from the name yet name no market, so the veto would
    silently stop seeing a contradiction. The two tables are hand-written,
    not derived, so this guard is what keeps them in step.
    """
    unmapped = set(resolve._COUNTRY_TOKENS) - (
        set(resolve._MARKET_BY_TOKEN) | set(resolve._REGIONAL_MARKET_TOKENS)
    )
    assert unmapped == set(), f"country tokens with no market mapping: {unmapped}"


def test_ambiguous_candidate_list_is_capped():
    """A wide tie reports `ambiguous` but does not return every tied page.

    The list is a diagnostic, not an inventory: with more tied pages than
    ``MAX_CANDIDATES`` the tie is still reported, and the list is bounded.
    Country-qualified variants all score 0.80 and rank alike when no market is
    requested, which is exactly the wide-tie case.
    """
    tokens = sorted(resolve._COUNTRY_TOKENS)[: resolve.MAX_CANDIDATES + 5]
    names = [f"Burger King {token}" for token in tokens]
    assert len(names) > resolve.MAX_CANDIDATES
    result = resolve.resolve_advertiser("Burger King", names)
    assert result["error"] == "name_not_matched"
    assert result["ambiguous"] is True
    assert len(result["candidates"]) == resolve.MAX_CANDIDATES
    assert all(c["score"] == 0.80 for c in result["candidates"])
