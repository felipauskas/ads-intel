"""Advertiser name resolution: score a page name against a target brand.

Ported from ``ad_intel.resolve`` (marketing-engineering), but name rungs only:
B has no ``page_id`` or handle, so A's 1.00 / 0.90 / 0.88 plateaus are out of
scope and its 0.70 rung (handle containment) has no analogue here. What is
kept is A's name ladder and its threshold:

* ``0.85`` normalized name — ``re.sub(r"[^a-z0-9]", "", name)`` on both sides
* ``0.80`` exact name, including a page that differs only by a trailing
  country qualifier (``Burger King Arabia`` == ``Burger King``)
* ``0.60`` substring containment (normalized or raw), same as A's name rung

One deliberate divergence from A: A tests the normalized rung *before* the
exact one, so identical strings score 0.85 there. Here exact is tested first,
so an identical name scores 0.80 and only a spelled-differently variant
(``KFC`` vs ``K.F.C.``) reaches 0.85. That is what A's own constants imply
(exact == 0.80) and it keeps the ladder monotone: no rung can outscore a
stricter one.

A second divergence is behavioural, not numeric: when nothing reaches
``MATCH_THRESHOLD`` A silently degrades to "no rows" (its status write is
gated on a DB connection the CLI caller never passes). Here the mismatch is
returned to the caller as ``name_not_matched`` with the scored candidates, so
a keyword hit is never mistaken for the advertiser.

Because the country rung deliberately scores a qualified page the same as the
bare brand, equal scores are common and must not be settled by listing order.
Two tie-breakers run after score — the page's country qualifier being the
requested market, then the page name being exactly the target — and a tie that
survives both is reported (``"ambiguous": True``) instead of guessed. A
requested market also filters out, *before* ranking, any page that explicitly
names a different market (a truthful ``name_not_matched``, never a
wrong-market PASS).

Pure stdlib, pure functions over dicts.
"""

import re
import unicodedata

MATCH_THRESHOLD = 0.80

_NON_ALNUM = re.compile(r"[^a-z0-9]")

#: Trailing tokens that qualify *where* a page operates, not *who* it is.
#: `Burger King Arabia` / `Pizza Hut KSA` are the same advertiser as their
#: bare brand names; scoring them as substring 0.60 rejected the correct page.
#: Stripping is trailing-only and case/accent-folded. Full country names and
#: the codes that show up in page names are both listed; multi-word names work
#: because the loop peels one token at a time ("Saudi Arabia" -> "Saudi").
_COUNTRY_TOKENS = frozenset(
    {
        # Gulf / Middle East
        "ae", "arabia", "bahrain", "bh", "emirates", "jordan", "jo",
        "ksa", "kuwait", "kw", "lebanon", "lb", "oman", "om", "qatar",
        "qa", "sa", "saudi", "uae",
        # Africa / Asia
        "eg", "egypt", "india", "malaysia", "pakistan", "pk",
        # North America / Europe
        "canada", "ca", "gb", "uk", "united", "kingdom", "us", "usa",
        "spain", "espana", "es",
    }
)

_WORD = re.compile(r"[^\W_]+", re.UNICODE)

#: Which market a trailing qualifier names: the ISO-3166 code the tool's
#: ``country`` argument uses, so a page can be compared with the requested
#: market. This table is written out by hand, not derived from
#: ``_COUNTRY_TOKENS``: the two sets are closely related but not identical
#: (``_COUNTRY_TOKENS`` holds the words a page name can end with, while a
#: regional word like ``arabia`` has no single market and lives in
#: ``_REGIONAL_MARKET_TOKENS``). Every token in ``_COUNTRY_TOKENS`` must be
#: accounted for by one of the two mappings, which
#: ``tests/test_resolve.py`` guards: a token with no market entry would be
#: stripped from the name yet name no market, silently disarming the veto.
#: Codes with no canonical market (``united``/``kingdom`` are GB) are spelled
#: out rather than guessed from the two-letter prefix.
_MARKET_BY_TOKEN = {
    "ae": "AE", "uae": "AE", "emirates": "AE",
    "sa": "SA", "ksa": "SA", "saudi": "SA",
    "bh": "BH", "bahrain": "BH",
    "jo": "JO", "jordan": "JO",
    "kw": "KW", "kuwait": "KW",
    "lb": "LB", "lebanon": "LB",
    "om": "OM", "oman": "OM",
    "qa": "QA", "qatar": "QA",
    "eg": "EG", "egypt": "EG",
    "india": "IN", "malaysia": "MY", "pk": "PK", "pakistan": "PK",
    "ca": "CA", "canada": "CA",
    "gb": "GB", "uk": "GB", "united": "GB", "kingdom": "GB",
    "us": "US", "usa": "US",
    "es": "ES", "spain": "ES", "espana": "ES",
}

#: Qualifiers that name a *region*, not one country.
#:
#: ``arabia`` is a Gulf-regional word: ``Burger King Arabia`` is the page the
#: UAE library returns for an AE query (recorded PASS pair ``burger-king-ae``),
#: so mapping it to SA alone vetoed a correct AE resolution. It is treated as
#: compatible with the GCC markets below. Trade-off: because SA is in the set,
#: a page named ``... Arabia`` also resolves for a Saudi query; that is
#: acceptable because the word denotes the Arabian peninsula, not Saudi Arabia
#: exclusively. A page that names a *specific* country (``Saudi Arabia``,
#: ``Pizza Hut KSA``) is still pinned to that country — the specific token
#: wins over the regional one.
_REGIONAL_MARKET_TOKENS = {
    "arabia": frozenset({"AE", "SA", "BH", "KW", "OM", "QA"}),
}



def _strip_trailing_countries(name) -> tuple[str, bool]:
    """Drop trailing country-qualifier tokens, returning spaced words.

    ``"Burger King Arabia"`` -> ``("burger king", True)``;
    ``"Pizza Hut Saudi Arabia"`` -> ``("pizza hut", True)`` (one token peeled
    at a time). A name that is nothing but qualifiers is left intact so
    stripping can never empty it.
    """
    text = str(name or "").strip().lower()
    tokens = _WORD.findall(text)
    original = list(tokens)
    while len(tokens) > 1 and normalize(tokens[-1]) in _COUNTRY_TOKENS:
        tokens.pop()
    return " ".join(tokens), tokens != original


def _trailing_markets(name) -> frozenset[str]:
    """Market codes named by a page's trailing country qualifier.

    ``"Burger King Malaysia"`` -> ``{"MY"}``; ``"Pizza Hut KSA"`` -> ``{"SA"}``;
    ``"Burger King Arabia"`` -> the GCC set it regionalises to; a page with no
    qualifier -> the empty set. Same trailing-only peeling as
    ``_strip_trailing_countries``, but it reports *which* market was named so a
    candidate can be compared with the requested one.

    A specific country token outranks a regional one: ``"Burger King Saudi
    Arabia"`` peels both words, and the explicit ``saudi`` pins it to SA
    instead of widening it to the Gulf.
    """
    tokens = _WORD.findall(str(name or "").strip().lower())
    specific = set()
    regional = set()
    while len(tokens) > 1 and normalize(tokens[-1]) in _COUNTRY_TOKENS:
        token = normalize(tokens.pop())
        code = _MARKET_BY_TOKEN.get(token)
        if code:
            specific.add(code)
        else:
            regional |= _REGIONAL_MARKET_TOKENS.get(token, frozenset())
    return frozenset(specific or regional)


def _identity_rank(target, page_name, market=None) -> tuple[int, ...]:
    """Tie-breakers applied *after* score.

    Both components are higher-is-better and only decide between candidates
    that already scored the same; the numeric ladder (0.80 / 0.85 / 0.60) is
    untouched.

    * market — ``2`` when the page's country qualifier is the requested
      market, ``1`` when the page names no country (nothing contradicts the
      request), ``0`` when it names a different one. Only present when the
      caller supplies a market: without one there is nothing to compare.
    * exact — ``2`` when the page name is the target with no added qualifier
      (case/punctuation aside), ``1`` otherwise.

    When a market is requested it is the *first* key: the live sweep asked for
    EG and picked ``Burger King Malaysia`` over ``Burger King Egypt`` because
    "exact" ran first. For a market-scoped query the market match is the
    stronger signal; exactness still decides a tie (and still decides alone
    when no market is requested).
    """
    exact = 2 if normalize(page_name) == normalize(target) else 1
    wanted = str(market or "").strip().upper()
    if not wanted:
        return (exact,)
    markets = _trailing_markets(page_name)
    if not markets:
        matched = 1
    elif wanted in markets:
        matched = 2
    else:
        matched = 0
    return (matched, exact)


def _names_other_market(page_name, market) -> bool:
    """True when the page explicitly qualifies a market other than ``market``.

    A page with *no* qualifier is global and acceptable for any requested
    market; only an explicit contradiction is vetoed. ``market`` absent means
    the caller does not know the market, so nothing can contradict it.
    """
    wanted = str(market or "").strip().upper()
    if not wanted:
        return False
    markets = _trailing_markets(page_name)
    return bool(markets) and wanted not in markets



def _dedupe_by_page(candidates):
    """Keep the first (best) candidate per normalized page name."""
    seen_pages = set()
    unique = []
    for candidate in candidates:
        page = normalize(candidate["page_name"])
        if page not in seen_pages:
            seen_pages.add(page)
            unique.append(candidate)
    return unique


#: Cap on the diagnostic candidate list returned with a mismatch, including
#: the ambiguous-tie list: the result is a diagnostic, not an inventory, and an
#: unbounded list can carry a whole rendered page's worth of pages.
MAX_CANDIDATES = 10


def normalize(name) -> str:
    """Lowercase, fold accents, strip everything but ``a-z0-9``.

    NFKD decomposition is required before dropping non-alphanumerics: without
    it ``L'Oréal`` loses the accented ``é`` and normalizes to ``loral`` instead
    of ``loreal``. A's original normalization skipped this and mismatched
    accented page names.
    """
    text = unicodedata.normalize("NFKD", str(name or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return _NON_ALNUM.sub("", text)


def score_candidate(target, page_name) -> float:
    """Score how well ``page_name`` matches the ``target`` brand name."""
    raw_target = str(target or "").strip().lower()
    raw_name = str(page_name or "").strip().lower()
    if not raw_target or not raw_name:
        return 0.0

    norm_target = normalize(raw_target)
    norm_name = normalize(raw_name)
    if not norm_target or not norm_name:
        return 0.0

    if raw_name == raw_target:
        return 0.80

    # Compare the advertiser core, not the geographic qualifier: the correct
    # page for a brand is routinely named "<Brand> <Country>".
    target_core, target_stripped = _strip_trailing_countries(raw_target)
    name_core, name_stripped = _strip_trailing_countries(raw_name)
    if (target_stripped or name_stripped) and target_core == name_core:
        return 0.80
    if normalize(target_core) == normalize(name_core):
        return 0.85
    if norm_target in norm_name or raw_target in raw_name:
        return 0.60
    return 0.0


def resolve_advertiser(target, page_names, market=None) -> dict:
    """Pick the winning page name, or report the mismatch.

    Returns ``{"page_name", "score"}`` on a match at or above
    ``MATCH_THRESHOLD``; otherwise ``{"error": "name_not_matched", "target",
    "candidates", "threshold"}`` with candidates sorted best-first.

    Score alone is ambiguous by design: exact, country-qualified and
    spelled-variant pages all land on 0.80, and two of them used to be decided
    by listing order (live sweep: ``Burger King Malaysia`` won a market-EG
    search). Ties are now broken by ``_identity_rank`` — the requested
    ``market`` first, then exact name — and a tie that survives both is *not*
    resolved: the mismatch is returned with ``"ambiguous": True`` and the tied
    candidates, so the caller can ask the user which page they meant. That
    candidate list is bounded at ``MAX_CANDIDATES`` in listing order; when
    more pages tie than that, ``"ambiguous": True`` still reports the tie, but
    the list is a bounded sample rather than every tied page.

    A requested ``market`` also *filters out* every page that explicitly names
    another one: the single recorded ``burger-king-eg`` candidate is ``Burger
    King Malaysia``, and resolving it for EG was a false PASS. Filtering
    happens before ranking, so a contradicting page cannot shadow an eligible
    one just by scoring higher. A page with no qualifier is global and stays
    eligible; a page qualified with the requested market stays eligible. When
    every candidate is filtered out, the ``name_not_matched`` result lists
    those candidates as diagnostics.

    With ``market=None`` nothing is filtered or ranked by market — but this is
    *not* the legacy behaviour verbatim: ties still fall back to exact-name
    first and are still reported as ``ambiguous`` instead of being settled by
    listing order.

    The ``name_not_matched`` code is kept (callers in ``tools.py`` branch on
    ``"error" in resolution``) rather than adding a new result kind.
    """
    target = str(target or "").strip()
    # A market-scoped query must not resolve to a page that explicitly names
    # a different market — a truthful FAIL beats a false PASS. This is a
    # *filter*, not a check on the winner: a wrong-market page that happens to
    # score higher (e.g. ``K.F.C. Malaysia`` at 0.85) must not shadow the
    # correct ``KFC Egypt`` at 0.80 just because score dominates rank.
    wanted = str(market or "").strip().upper()
    scored = []
    excluded = []
    for name in page_names or []:
        name = str(name or "")
        if not name.strip():
            continue
        score = score_candidate(target, name)
        if score <= 0:
            continue
        candidate = {
            "page_name": name,
            "score": score,
            "rank": _identity_rank(target, name, market),
        }
        if wanted and _names_other_market(name, market):
            excluded.append(candidate)
        else:
            scored.append(candidate)

    scored.sort(key=lambda c: (c["score"], c["rank"]), reverse=True)
    excluded.sort(key=lambda c: c["score"], reverse=True)
    # One candidate per page: six ads from the same page used to fill six of
    # the ten diagnostic slots. Sorted best-first, so the first hit per page
    # is the best-scoring one.
    scored = _dedupe_by_page(scored)
    excluded = _dedupe_by_page(excluded)

    if not scored and excluded:
        # Every plausible page contradicted the requested market. Report the
        # evidence so the caller can see *why* nothing resolved.
        return {
            "error": "name_not_matched",
            "target": target,
            "candidates": [
                {"page_name": c["page_name"], "score": c["score"]}
                for c in excluded[:MAX_CANDIDATES]
            ],
            "threshold": MATCH_THRESHOLD,
        }

    if scored and scored[0]["score"] >= MATCH_THRESHOLD:
        top = scored[0]
        tied = [
            c
            for c in scored
            if (c["score"], c["rank"]) == (top["score"], top["rank"])
        ]
        if len(tied) > 1:
            # Ambiguity reports only the tied set: a 0.60 runner-up must not
            # masquerade as an equally plausible page. The list is still
            # bounded — MAX_CANDIDATES is a diagnostic cap, and `ambiguous`
            # alone already states that the tie exists.
            return {
                "error": "name_not_matched",
                "target": target,
                "candidates": [
                    {"page_name": c["page_name"], "score": c["score"]}
                    for c in tied[:MAX_CANDIDATES]
                ],
                "threshold": MATCH_THRESHOLD,
                "ambiguous": True,
            }
        return {"page_name": top["page_name"], "score": top["score"]}

    return {
        "error": "name_not_matched",
        "target": target,
        "candidates": [
            {"page_name": c["page_name"], "score": c["score"]}
            for c in scored[:MAX_CANDIDATES]
        ],
        "threshold": MATCH_THRESHOLD,
    }


def filter_ads(ads, target, market=None):
    """Split ads by advertiser: ``(resolution, ads_on_winning_page)``.

    Ads are matched on the *normalized* page name, not the raw string: the
    library renders one page as ``K.F.C.``, ``KFC`` or `` kfc ``, and a raw
    equality check dropped every variant but the winner's spelling.

    ``market`` is the requested two-letter market, forwarded to resolution: a
    page country-qualified for that market outranks one qualified for another,
    and a page that explicitly names a different market is vetoed outright
    (never traded off against a higher score).
    """
    ads = list(ads or [])
    resolution = resolve_advertiser(
        target, [ad.get("page_name") for ad in ads], market=market
    )
    if "error" in resolution:
        return resolution, []
    winner = normalize(resolution["page_name"])
    kept = [ad for ad in ads if normalize(ad.get("page_name")) == winner]
    return resolution, kept
