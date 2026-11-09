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
    """A qualifier peeled from a page name must be explainable as a market.

    ``_COUNTRY_TOKENS`` drives stripping (which decides what counts as a
    country qualifier); ``_MARKET_BY_PHRASE`` / ``_REGIONAL_MARKET_TOKENS``
    drive the market veto. A peelable key with no mapping would strip from the
    name yet name no market, so the veto would silently stop seeing a
    contradiction. This is checked *behaviourally* — peel the token off a page
    name and require a non-empty market set — so it also covers the multi-word
    phrases ("Saudi Arabia", "United Arab Emirates") the peeler now matches as
    units, not just the single words in ``_COUNTRY_TOKENS``.
    """
    keys = set(resolve._MARKET_BY_PHRASE) | set(resolve._REGIONAL_MARKET_TOKENS)
    # Two-letter ISO codes that double as English words only peel in all-caps
    # form, so the probe must print them the way a page does (``KFC IN``).
    ambiguous = resolve._AMBIGUOUS_TWO_LETTER_CODES
    unmapped = sorted(
        key
        for key in keys
        if not resolve._trailing_markets(
            f"Burger King {key.upper() if key in ambiguous else key}"
        )
    )
    assert unmapped == [], f"qualifiers with no market mapping: {unmapped}"
    # The bare-word set is a subset of the keys above and must stay one.
    assert set(resolve._COUNTRY_TOKENS) <= keys


def test_ambiguous_candidate_list_is_capped():
    """A wide tie reports `ambiguous` but does not return every tied page.

    The list is a diagnostic, not an inventory: with more tied pages than
    ``MAX_CANDIDATES`` the tie is still reported, and the list is bounded.
    Country-qualified variants all score 0.80 and rank alike when no market is
    requested, which is exactly the wide-tie case.
    """
    tokens = sorted(resolve._COUNTRY_TOKENS)
    ambiguous = resolve._AMBIGUOUS_TWO_LETTER_CODES
    # Print ambiguous codes the way a page does (``KFC IN``): lowercase prose
    # is deliberately not peeled, so it would not be a 0.80 candidate.
    names = [
        f"Burger King {token.upper() if token in ambiguous else token}"
        for token in tokens
    ][: resolve.MAX_CANDIDATES + 5]
    assert len(names) > resolve.MAX_CANDIDATES
    result = resolve.resolve_advertiser("Burger King", names)
    assert result["error"] == "name_not_matched"
    assert result["ambiguous"] is True
    assert len(result["candidates"]) == resolve.MAX_CANDIDATES
    assert all(c["score"] == 0.80 for c in result["candidates"])


# ---------------------------------------------------------------------------
# F5: full ISO-3166 market table and multi-word qualifier peeling.
# ---------------------------------------------------------------------------

#: The 25 live-matrix pairs recorded at commit 233b266 (5 brands x AE/SA/EG/
#: US/GB), with the resolution each produced *before* the ISO table was added.
#: This is the regression pin for the task: widening the country table must
#: not change which pairs resolve. Page names and URLs come from ``search``
#: then ``advertiser_search``, in that order, exactly as the replay below
#: reads them; ads are replayed through ``filter_ads`` so the URL slug counts.
#:
#: One entry moved by design, not by accident: ``kfc-eg`` still resolves at
#: 0.80, but the winner is now ``KFC Masr`` (the Egyptian page) instead of the
#: bare ``KFC`` page, because ``masr`` is a requested alias and therefore
#: ranks as a market match. Same PASS, more specific page.
#:
#: Four verdicts differ from the listing pinned at 233b266. Three are input
#: drift (the 3c4acfc recording holds pages that listing did not) and one is
#: the slug veto:
#:
#: * ``kfc-us`` now ``name_not_matched`` — the only ``KFC``-named page is
#:   ``facebook.com/KFCMexico/``; the slug names MX, so the ad is vetoed. This
#:   is the wrong-page PASS the slug veto exists to remove.
#: * ``burger-king-us`` now ``Burger King`` — the current listing contains the
#:   global ``facebook.com/burgerking/`` page, which 233b266 did not have.
#: * ``burger-king-gb`` now ``Burger King UK`` — the current listing contains
#:   ``facebook.com/burgerkinguk/`` (GB), absent at 233b266.
#: * ``mcdonalds-eg`` now ``McDonald's`` — the current listing contains
#:   ``facebook.com/McDonaldsEgypt/`` (EG); the Omani ``McDonaldsOM`` ads that
#:   used to dominate it are vetoed.
MATRIX_25_GOLDEN = {
    "burger-king-ae": ("Burger King Arabia", 0.80),
    "burger-king-eg": "name_not_matched",
    "burger-king-gb": ("Burger King UK", 0.80),
    "burger-king-sa": ("Burger King Arabia", 0.80),
    "burger-king-us": ("Burger King", 0.80),
    "dominos-pizza-ae": ("Domino's Pizza", 0.80),
    "dominos-pizza-eg": ("Domino's Pizza", 0.80),
    "dominos-pizza-gb": ("Domino's Pizza", 0.80),
    "dominos-pizza-sa": ("Domino's Pizza", 0.80),
    "dominos-pizza-us": ("Domino's Pizza", 0.80),
    "kfc-ae": ("KFC", 0.80),
    "kfc-eg": ("KFC Masr", 0.80),
    "kfc-gb": ("KFC", 0.80),
    "kfc-sa": ("KFC", 0.80),
    "kfc-us": "name_not_matched",
    "mcdonalds-ae": ("McDonald's", 0.80),
    "mcdonalds-eg": ("McDonald's", 0.80),
    "mcdonalds-gb": ("McDonald's", 0.80),
    "mcdonalds-sa": ("McDonald's", 0.80),
    "mcdonalds-us": ("McDonald's", 0.80),
    "pizza-hut-ae": ("Pizza Hut", 0.80),
    "pizza-hut-eg": ("Pizza Hut", 0.80),
    "pizza-hut-gb": ("Pizza Hut", 0.80),
    "pizza-hut-sa": ("Pizza Hut KSA", 0.80),
    "pizza-hut-us": ("Pizza Hut", 0.80),
}


def _matrix_pairs():
    """(folder, brand, country, ads) for every recorded 25-pair folder."""
    if not LIVE_MATRIX.is_dir():
        pytest.skip(f"live-matrix missing: {LIVE_MATRIX}")
    pairs = []
    for folder in sorted(MATRIX_25_GOLDEN):
        path = LIVE_MATRIX / folder / "ads.json"
        if not path.is_file():
            pytest.skip(f"live-matrix recording missing: {path}")
        data = json.loads(path.read_text())
        ads = []
        for field in ("search", "advertiser_search"):
            for ad in data.get(field) or []:
                if isinstance(ad, dict) and ad.get("page_name"):
                    ads.append(ad)
        pairs.append((folder, data["brand"], data["country"], ads))
    return pairs


def test_matrix_25_replay_is_unchanged():
    """Replay every recorded pair; the 25-pair verdicts must not drift.

    The replay goes through ``filter_ads``, not ``resolve_advertiser``: the
    verdict now depends on ``page_url`` as well as ``page_name``, because a
    same-named page's slug is the only thing that says which market it serves.
    """
    pairs = _matrix_pairs()
    assert len(pairs) == 25
    assert set(MATRIX_25_GOLDEN) == {folder for folder, *_ in pairs}

    actual = {}
    for folder, brand, country, ads in pairs:
        result, _ = resolve.filter_ads(ads, brand, market=country)
        if "error" in result:
            actual[folder] = "name_not_matched"
        else:
            actual[folder] = (result["page_name"], result["score"])

    assert actual == MATRIX_25_GOLDEN


def test_matrix_25_never_resolves_a_conflicting_market():
    """Every resolved ad is eligible by both name and URL slug."""
    for folder, brand, country, ads in _matrix_pairs():
        result, kept = resolve.filter_ads(ads, brand, market=country)
        if "error" in result:
            continue
        markets = resolve._trailing_markets(result["page_name"])
        assert not markets or country in markets, f"{folder}: {result}"
        for ad in kept:
            slug_markets = resolve._slug_markets(ad.get("page_url"), brand)
            assert not slug_markets or country in slug_markets, (
                f"{folder}: kept {ad.get('page_url')} naming {slug_markets} "
                f"for {country}"
            )


def test_iso_table_covers_all_249_countries():
    """Every officially assigned ISO-3166-1 country maps to its alpha-2 code."""
    table = resolve._ISO_COUNTRY_NAMES
    assert len(table) == 249
    codes = list(table.values())
    assert len(codes) == len(set(codes))
    assert all(isinstance(code, str) and len(code) == 2 for code in codes)
    # Spot checks across the range, not just the markets the matrix covers.
    assert table["france"] == "FR"
    assert table["germany"] == "DE"
    assert table["philippines"] == "PH"
    assert table["mexico"] == "MX"
    assert table["japan"] == "JP"
    assert table["zimbabwe"] == "ZW"


@pytest.mark.parametrize(
    "name, market",
    [
        ("France", "FR"),
        ("Germany", "DE"),
        ("Philippines", "PH"),
        ("Mexico", "MX"),
        ("Japan", "JP"),
        ("Nigeria", "NG"),
        ("Colombia", "CO"),
        ("Poland", "PL"),
        ("Viet Nam", "VN"),
        ("Cote d'Ivoire", "CI"),
    ],
)
def test_iso_country_name_peels_and_resolves(name, market):
    """Any ISO country name may qualify a page, end to end."""
    page = f"KFC {name}"
    assert resolve.score_candidate("KFC", page) >= 0.80
    assert resolve.resolve_advertiser("KFC", [page], market=market) == {
        "page_name": page,
        "score": 0.80,
    }


@pytest.mark.parametrize(
    "name, market",
    [
        ("Masr", "EG"),          # Arabic endonym for Egypt
        ("Deutschland", "DE"),   # German
        ("Espana", "ES"),        # Spanish, unaccented
        ("Italia", "IT"),        # Italian
        ("Mexico", "MX"),        # Spanish, unaccented
        ("Brasil", "BR"),        # Portuguese
        ("Turkiye", "TR"),       # Turkish endonym
        ("Nederland", "NL"),     # Dutch
        ("Pilipinas", "PH"),     # Filipino
    ],
)
def test_endonym_aliases_peel_and_resolve(name, market):
    page = f"KFC {name}"
    assert resolve.score_candidate("KFC", page) >= 0.80
    result = resolve.resolve_advertiser("KFC", [page], market=market)
    assert result == {"page_name": page, "score": 0.80}


@pytest.mark.parametrize(
    "name, market",
    [
        ("Saudi Arabia", "SA"),
        ("United Arab Emirates", "AE"),
        ("United Kingdom", "GB"),
        ("South Africa", "ZA"),
        ("New Zealand", "NZ"),
        ("South Korea", "KR"),
        ("Sri Lanka", "LK"),
        ("Costa Rica", "CR"),
        ("El Salvador", "SV"),
        ("Trinidad and Tobago", "TT"),
        ("Papua New Guinea", "PG"),
        ("United States", "US"),
    ],
)
def test_multiword_country_names_peel_as_whole_phrases(name, market):
    """Multi-word names peel completely: no leftover words in the brand core.

    Peeling only the last token would leave ``United Arab`` glued to the brand
    and drop the score to the 0.60 substring rung.
    """
    page = f"Burger King {name}"
    core, stripped = resolve._strip_trailing_countries(page)
    assert (core, stripped) == ("burger king", True)
    assert resolve._trailing_markets(page) == {market}
    assert resolve.score_candidate("Burger King", page) >= 0.80
    assert resolve.resolve_advertiser("Burger King", [page], market=market) == {
        "page_name": page,
        "score": 0.80,
    }


def test_f5_markets_that_used_to_score_zero_sixty_now_resolve():
    """KFC France / McDonald's Deutschland / KFC Philippines / KFC Mexico.

    All four scored 0.60 (substring) before the ISO table existed, so they
    were rejected at the 0.80 threshold as ``name_not_matched``.
    """
    cases = [
        ("KFC", "KFC France", "FR"),
        ("McDonald's", "McDonald's Deutschland", "DE"),
        ("KFC", "KFC Philippines", "PH"),
        ("KFC", "KFC Mexico", "MX"),
    ]
    for brand, page, market in cases:
        result = resolve.resolve_advertiser(brand, [page], market=market)
        assert "error" not in result, (brand, page, result)
        assert result["page_name"] == page
        assert result["score"] >= 0.80


def test_wrong_market_page_is_still_vetoed_after_widening():
    """A French page cannot satisfy a German query, however well it scores."""
    result = resolve.resolve_advertiser("KFC", ["KFC France"], market="DE")
    assert result["error"] == "name_not_matched"
    assert result["candidates"] == [{"page_name": "KFC France", "score": 0.80}]

    result = resolve.resolve_advertiser(
        "McDonald's", ["McDonald's Deutschland"], market="FR"
    )
    assert result["error"] == "name_not_matched"


def test_bare_page_still_resolves_in_any_market_after_widening():
    for market in ("FR", "DE", "PH", "MX", "JP", "NG"):
        assert resolve.resolve_advertiser("KFC", ["KFC"], market=market) == {
            "page_name": "KFC",
            "score": 0.80,
        }


# ---------------------------------------------------------------------------
# ISO spec review: a qualifier inside the brand name is not a market claim.
# ---------------------------------------------------------------------------

#: Brands whose *name* ends in a country word. The trailing phrase is part of
#: the brand, so a US-scoped query must not read it as a non-US page.
BRAND_QUALIFIER_NAMES = ["Little Italy", "Air New Zealand", "Bank of Georgia"]


@pytest.mark.parametrize("brand", BRAND_QUALIFIER_NAMES)
def test_brand_ending_in_country_word_is_not_vetoed_for_other_market(brand):
    """``Little Italy`` for US: the ``Italy`` in the name is brand, not market.

    Before the fix the page peeled ``italy`` -> IT and vetoed the brand's own
    page for a US query (``name_not_matched``). The target carries the same
    qualifier, so the page is an exact brand page and must resolve.
    """
    assert resolve._trailing_markets(brand)  # the qualifier really is peeled
    assert resolve.resolve_advertiser(brand, [brand], market="US") == {
        "page_name": brand,
        "score": 0.80,
    }


@pytest.mark.parametrize(
    "brand, market",
    [
        ("Little Italy", "IT"),
        ("Air New Zealand", "NZ"),
        ("Bank of Georgia", "GE"),
    ],
)
def test_brand_ending_in_country_word_resolves_in_that_market(brand, market):
    """For ``Air New Zealand`` in NZ the page *is* the local page."""
    assert resolve.resolve_advertiser(brand, [brand], market=market) == {
        "page_name": brand,
        "score": 0.80,
    }


def test_foreign_qualifier_on_brand_page_still_vetoed():
    """Control: an *extra* qualifier the target does not carry is a real claim.

    ``Air New Zealand`` carries ``New Zealand``; a page that adds ``Australia``
    names a market the brand does not, so it stays a truthful FAIL for US.
    """
    page = "Air New Zealand Australia"
    assert resolve._trailing_markets(page) == {"NZ", "AU"}
    result = resolve.resolve_advertiser("Air New Zealand", [page], market="US")
    assert result["error"] == "name_not_matched"


def test_page_qualifier_outside_target_still_vetoed():
    """Control: ``Burger King Malaysia`` cannot satisfy an EG query.

    ``Burger King`` carries no qualifier, so the page's ``Malaysia`` is a
    market claim and the veto is unchanged by the target-aware fix.
    """
    result = resolve.resolve_advertiser("Burger King", ["Burger King Malaysia"], market="EG")
    assert result["error"] == "name_not_matched"
    assert result["candidates"] == [{"page_name": "Burger King Malaysia", "score": 0.80}]


# ---------------------------------------------------------------------------
# ISO re-review Gap 1: a peeled *target* core must not collapse to a generic
# word and match a different brand.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target, page, market",
    [
        ("Air France", "Air Canada", "CA"),
        ("Air France", "Air India", "IN"),
        ("Air New Zealand", "Air China", "CN"),
    ],
)
def test_swapping_the_targets_country_word_is_not_a_match(target, page, market):
    """Peeling the *target* collapsed both cores to ``air`` -> 0.80 false PASS.

    ``Air France`` has core ``air`` once ``france`` is peeled, and so does
    ``Air Canada``; core equality alone therefore resolved a different
    airline. All three scored 0.0 on HEAD (the unguarded 0.80 was an
    intermediate state of this fix) and must stay truthful misses.
    """
    assert resolve.score_candidate(target, page) < 0.80
    result = resolve.resolve_advertiser(target, [page], market=market)
    assert result["error"] == "name_not_matched"
    assert "page_name" not in result


@pytest.mark.parametrize(
    "target, page, market",
    [
        ("Air France", "Air France Canada", "CA"),
        ("Air France", "Air France Egypt", "EG"),
        ("Air New Zealand", "Air New Zealand Australia", "AU"),
    ],
)
def test_brand_qualifier_may_be_extended_by_an_added_market(target, page, market):
    """The rule is "add, never replace": keeping the brand's country word is fine.

    These pages exist in the wild (an airline's local pages). They keep the
    target's own qualifier, so the core rungs stay available and the page
    resolves for the market it adds. ``Air New Zealand Australia`` is still a
    truthful FAIL for US — that is the market veto's job, not the score's.
    """
    assert resolve.score_candidate(target, page) == 0.80
    assert resolve.resolve_advertiser(target, [page], market=market) == {
        "page_name": page,
        "score": 0.80,
    }
    assert resolve.resolve_advertiser(target, [page], market="US")["error"] == (
        "name_not_matched"
    )


def test_qualifier_preservation_is_the_guard():
    """Direct check of the predicate that gates the core rungs."""
    assert resolve._qualifiers_preserved("Air France", "Air France Canada") is True
    assert resolve._qualifiers_preserved("Air France", "Air Canada") is False
    assert resolve._qualifiers_preserved("Air New Zealand", "Air China") is False
    # A target with no country word is unconstrained: the page may add one.
    assert resolve._qualifiers_preserved("Burger King", "Burger King Malaysia") is True


# ---------------------------------------------------------------------------
# ISO re-review Gap 1 (regressed from HEAD): a page with *no* trailing market
# qualifier is the global page and satisfies every target qualifier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target, page, market",
    [
        ("KFC Saudi Arabia", "KFC", "SA"),
        ("KFC Egypt", "KFC", "EG"),
        ("Pizza Hut Saudi Arabia", "Pizza Hut", "SA"),
        ("Air France Canada", "Air France", "CA"),
    ],
)
def test_bare_page_satisfies_a_market_qualified_target(target, page, market):
    """The user wrote the market into the advertiser string; the brand page is right.

    A page that drops the qualifier is not a mismatch: ``KFC`` is KFC's global
    page and the correct resolution for ``KFC Saudi Arabia``. The subset check
    on peeled *phrases* read the dropped phrase as a contradiction and scored
    0.0 (HEAD scored 0.80).
    """
    assert resolve._trailing_markets(page) <= resolve._trailing_markets(target)
    assert resolve._qualifiers_preserved(target, page) is True
    assert resolve.score_candidate(target, page) == 0.80
    assert resolve.resolve_advertiser(target, [page], market=market) == {
        "page_name": page,
        "score": 0.80,
    }


# ---------------------------------------------------------------------------
# ISO re-review Gap 2: compare market *codes*, not phrase strings, so the same
# market spelled differently still preserves the qualifier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target, page, markets",
    [
        ("Pizza Hut Saudi Arabia", "Pizza Hut KSA", ("SA", "SA")),
        ("KFC UAE", "KFC United Arab Emirates", ("AE", "AE")),
        ("McDonald's United States", "McDonald's USA", ("US", "US")),
        ("KFC Egypt", "KFC Masr", ("EG", "EG")),
    ],
)
def test_same_market_spelled_differently_is_preserved(target, page, markets):
    """One market spelled two ways (``KSA``/``Saudi Arabia``) is preserved.

    ``UAE``/``United Arab Emirates``, ``USA``/``United States`` and
    ``Masr``/``Egypt`` are the other three shapes. The old check compared
    peeled *phrase strings*, so every one of these pairs scored 0.0; the
    predicate now compares market codes.
    """
    target_codes, page_codes = markets
    assert resolve._trailing_markets(target) == {target_codes}
    assert resolve._trailing_markets(page) == {page_codes}
    assert resolve._qualifiers_preserved(target, page) is True
    assert resolve.score_candidate(target, page) == 0.80
    assert resolve.resolve_advertiser(target, [page], market=page_codes) == {
        "page_name": page,
        "score": 0.80,
    }


@pytest.mark.parametrize(
    "target, page",
    [
        ("KFC Saudi Arabia", "KFC Egypt"),
        ("Pizza Hut Saudi Arabia", "Pizza Hut UAE"),
        ("Air France", "Air Canada"),
    ],
)
def test_different_market_is_still_not_preserved(target, page):
    """A page that names another market still rejects the qualifier."""
    assert not (resolve._trailing_markets(target) & resolve._trailing_markets(page))
    assert resolve._qualifiers_preserved(target, page) is False
    assert resolve.score_candidate(target, page) < 0.80


@pytest.mark.parametrize(
    "target, page, expected",
    [
        ("Little Italy", "Little Italy", 0.80),
        ("Air New Zealand", "Air New Zealand", 0.80),
        ("Burger King", "Burger King Malaysia", 0.80),
        ("KFC", "KFC Egypt", 0.80),
    ],
)
def test_legitimate_country_cases_keep_their_score(target, page, expected):
    """The fix must not cost the recorded PASS shapes anything."""
    assert resolve.score_candidate(target, page) == expected
    assert resolve.resolve_advertiser(target, [page]) == {
        "page_name": page,
        "score": expected,
    }


#: Two-letter ISO codes that are also common English words. ``Burger King me``
#: must not read as Montenegro; only the uppercase code is a market claim.
AMBIGUOUS_TWO_LETTER_CODES = sorted(resolve._AMBIGUOUS_TWO_LETTER_CODES)

#: Codes the ISO re-review named explicitly as still peeling in lowercase on
#: HEAD. Every one of them is an assigned ISO alpha-2 code and an ordinary
#: English word/token, so each must be guarded.
REQUIRED_AMBIGUOUS_CODES = {
    "us", "by", "am", "id", "ie", "ai", "la", "ma", "pa", "ne", "ye", "tv", "io",
}


def test_ambiguous_code_table_covers_every_english_word_code():
    """Gap 2: only 12 codes were guarded; the English-word codes are all here.

    Also asserts each entry really is an assigned ISO code that still peels in
    capitals, so the guard narrows prose peeling without losing a market.
    """
    guarded = resolve._AMBIGUOUS_TWO_LETTER_CODES
    assert REQUIRED_AMBIGUOUS_CODES <= guarded
    assigned = {code.lower(): code for code in resolve._ISO_COUNTRY_NAMES.values()}
    for code in guarded:
        assert code in assigned, f"{code!r} is not an assigned ISO alpha-2 code"
        assert resolve._trailing_markets(f"Burger King {code.upper()}") == {
            assigned[code]
        }


@pytest.mark.parametrize("code", AMBIGUOUS_TWO_LETTER_CODES)
def test_lowercase_english_word_is_not_peeled_as_country_code(code):
    assert resolve._trailing_markets(f"Burger King {code}") == frozenset()
    # Title case is prose too: only an all-caps token is the ISO code.
    assert resolve._trailing_markets(f"Burger King {code.capitalize()}") == frozenset()


def test_us_and_by_are_not_peeled_lowercase():
    """The two codes the review called out by name."""
    assert resolve._trailing_markets("Burger King us") == frozenset()
    assert resolve._trailing_markets("Burger King by") == frozenset()
    assert resolve._trailing_markets("Burger King US") == {"US"}
    assert resolve._trailing_markets("Burger King BY") == {"BY"}


def test_uppercase_two_letter_code_still_peels():
    """An uppercase code remains a market claim: ``KFC IN`` is India."""
    assert resolve._trailing_markets("Burger King IN") == {"IN"}
    assert resolve._trailing_markets("Burger King IT") == {"IT"}
    assert resolve.resolve_advertiser("Burger King", ["Burger King IT"], market="IT") == {
        "page_name": "Burger King IT",
        "score": 0.80,
    }


def test_uppercase_me_is_montenegro():
    """Documented semantics: uppercase ``ME`` is the ISO code, never prose.

    The word ``me`` is a pronoun, so any lowercase occurrence is left alone.
    All-caps is how a page prints a code (``KFC SA``), so ``Burger King ME``
    is Montenegro: it resolves for ME and is vetoed for another market.
    """
    assert resolve._trailing_markets("Burger King ME") == {"ME"}
    assert resolve.resolve_advertiser("Burger King", ["Burger King ME"], market="ME") == {
        "page_name": "Burger King ME",
        "score": 0.80,
    }
    assert (
        resolve.resolve_advertiser("Burger King", ["Burger King ME"], market="US")["error"]
        == "name_not_matched"
    )
    # Lowercase prose is not a market claim at all (fails the score rung, not
    # the market veto).
    assert resolve._names_other_market("Burger King me", "ME") is False


# ---------------------------------------------------------------------------
# Slug veto: page_url says which market a same-named page actually serves.
# ---------------------------------------------------------------------------

FB = "https://www.facebook.com/{slug}/"


@pytest.mark.parametrize(
    "slug, market, target",
    [
        ("KFCMexico", {"MX"}, "KFC"),
        ("McDonaldsOM", {"OM"}, "McDonald's"),
        ("McDonaldsUAE", {"AE"}, "McDonald's"),
        ("McDonaldsUK", {"GB"}, "McDonald's"),
        ("Pizzahutuae", {"AE"}, "Pizza Hut"),
        ("pizzahutoman", {"OM"}, "Pizza Hut"),
        ("pizzahutksaofficial", {"SA"}, "Pizza Hut"),
        ("PizzaHutSingapore", {"SG"}, "Pizza Hut"),
        ("mcdonaldshongkong", {"HK"}, "McDonald's"),
        ("mcdonaldsegypt", {"EG"}, "McDonald's"),
        ("KFCAustralia", {"AU"}, "KFC"),
        ("KFC.uk", {"GB"}, "KFC"),
        ("DominosUAE", {"AE"}, "Domino's Pizza"),
        ("dominospizzaindia", {"IN"}, "Domino's Pizza"),
        ("dominospizza.es", {"ES"}, "Domino's Pizza"),
        ("burgerkingksa", {"SA"}, "Burger King"),
        ("burgerkinguk", {"GB"}, "Burger King"),
    ],
)
def test_slug_markets_reads_camelcase_and_lowercase_handles(slug, market, target):
    assert resolve._slug_markets(FB.format(slug=slug), target) == frozenset(market)


def test_slug_arabia_is_regional_gcc():
    markets = resolve._slug_markets(FB.format(slug="kfcarabia"), "KFC")
    assert markets == resolve._REGIONAL_MARKET_TOKENS["arabia"]


@pytest.mark.parametrize(
    "slug, target",
    [
        ("McDonalds", "McDonald's"),
        ("mcd", "McDonald's"),
        ("capitalone", "Capital One"),
        ("ShaneHummus", "Shane Hummus"),
        ("61585938917376", "Burger King"),  # numeric page id
    ],
)
def test_slug_without_country_token_names_no_market(slug, target):
    assert resolve._slug_markets(FB.format(slug=slug), target) == frozenset()
    assert resolve._slug_names_other_market(FB.format(slug=slug), "US", target) is False


def test_slug_brand_country_word_is_not_a_market_claim():
    """``airnewzealand`` is the brand, not a New Zealand page for a US query."""
    url = FB.format(slug="airnewzealand")
    # The handle is the brand itself: no separate market claim, so it stays
    # eligible for every market. An added qualifier would still be a claim.
    assert resolve._slug_markets(url, "Air New Zealand") == frozenset()
    assert resolve._slug_names_other_market(url, "US", "Air New Zealand") is False
    added = FB.format(slug="airnewzealandaustralia")
    assert resolve._slug_markets(added, "Air New Zealand") == {"AU"}
    assert resolve._slug_names_other_market(added, "US", "Air New Zealand") is True


def test_slug_veto_flips_the_committed_kfc_us_rows():
    """``kfc-us`` kept ``facebook.com/KFCMexico/``; every KFC page is named KFC."""
    ads = [
        {"id": "1", "page_name": "KFC", "page_url": FB.format(slug="KFCMexico")},
        {"id": "2", "page_name": "KFC", "page_url": FB.format(slug="KFCMexico")},
    ]
    resolution, kept = resolve.filter_ads(ads, "KFC", market="US")
    assert resolution["error"] == "name_not_matched"
    assert kept == []


def test_slug_veto_drops_oman_for_saudi_but_keeps_global_and_numeric():
    ads = [
        {"id": "om", "page_name": "McDonald's", "page_url": FB.format(slug="McDonaldsOM")},
        {"id": "global", "page_name": "McDonald's", "page_url": FB.format(slug="McDonalds")},
        {"id": "numeric", "page_name": "McDonaldsksa_ws", "page_url": FB.format(slug="100070164136481")},
    ]
    resolution, kept = resolve.filter_ads(ads, "McDonald's", market="SA")
    assert resolution["page_name"] == "McDonald's"
    assert [ad["id"] for ad in kept] == ["global"]


def test_slug_veto_drops_oman_and_singapore_for_ae():
    ads = [
        {"id": "ae", "page_name": "Pizza Hut", "page_url": FB.format(slug="Pizzahutuae")},
        {"id": "om", "page_name": "Pizza Hut", "page_url": FB.format(slug="pizzahutoman")},
        {"id": "sg", "page_name": "Pizza Hut", "page_url": FB.format(slug="PizzaHutSingapore")},
    ]
    resolution, kept = resolve.filter_ads(ads, "Pizza Hut", market="AE")
    assert resolution["page_name"] == "Pizza Hut"
    assert [ad["id"] for ad in kept] == ["ae"]


def test_slug_veto_keeps_the_right_page_and_drops_the_wrong_one():
    ads = [
        {"id": "eg", "page_name": "McDonald's", "page_url": FB.format(slug="McDonaldsEgypt")},
        {"id": "om", "page_name": "McDonald's", "page_url": FB.format(slug="McDonaldsOM")},
    ]
    resolution, kept = resolve.filter_ads(ads, "McDonald's", market="EG")
    assert resolution["page_name"] == "McDonald's"
    assert [ad["id"] for ad in kept] == ["eg"]

    ads = [
        {"id": "gb", "page_name": "McDonald's", "page_url": FB.format(slug="McDonaldsUK")},
        {"id": "hk", "page_name": "McDonald's", "page_url": FB.format(slug="mcdonaldshongkong")},
    ]
    resolution, kept = resolve.filter_ads(ads, "McDonald's", market="GB")
    assert resolution["page_name"] == "McDonald's"
    assert [ad["id"] for ad in kept] == ["gb"]

    ads = [
        {"id": "au", "page_name": "KFC", "page_url": FB.format(slug="KFCAustralia")},
        {"id": "gb", "page_name": "KFC", "page_url": FB.format(slug="KFC.uk")},
    ]
    resolution, kept = resolve.filter_ads(ads, "KFC", market="GB")
    assert resolution["page_name"] == "KFC"
    assert [ad["id"] for ad in kept] == ["gb"]


def test_slug_veto_does_not_break_dominos_ae():
    """The name veto already drops India; the slug veto must keep UAE."""
    ads = [
        {"id": "ae", "page_name": "Domino's Pizza", "page_url": FB.format(slug="DominosUAE")},
        {"id": "in", "page_name": "Domino's Pizza India", "page_url": FB.format(slug="dominospizzaindia")},
    ]
    resolution, kept = resolve.filter_ads(ads, "Domino's Pizza", market="AE")
    assert resolution["page_name"] == "Domino's Pizza"
    assert [ad["id"] for ad in kept] == ["ae"]


def test_slug_veto_is_inert_without_a_market():
    ads = [
        {"id": "mx", "page_name": "KFC", "page_url": FB.format(slug="KFCMexico")},
    ]
    resolution, kept = resolve.filter_ads(ads, "KFC")
    assert resolution == {"page_name": "KFC", "score": 0.80}
    assert [ad["id"] for ad in kept] == ["mx"]
