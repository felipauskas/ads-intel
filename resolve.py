"""Advertiser name resolution: score a page name against a target brand.

Ported from ``ad_intel.resolve`` (marketing-engineering), but name rungs only:
B has no ``page_id`` or handle, so A's 1.00 / 0.90 / 0.88 plateaus are out of
scope and its 0.70 rung (handle containment) has no analogue here. What is
kept is A's name ladder and its threshold:

* ``0.85`` normalized name — ``re.sub(r"[^a-z0-9]", "", name)`` on both sides
* ``0.80`` exact name
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

Pure stdlib, pure functions over dicts.
"""

import re
import unicodedata

MATCH_THRESHOLD = 0.80

_NON_ALNUM = re.compile(r"[^a-z0-9]")

#: Cap on the diagnostic candidate list returned with a mismatch.
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
    if norm_name == norm_target:
        return 0.85
    if norm_target in norm_name or raw_target in raw_name:
        return 0.60
    return 0.0


def resolve_advertiser(target, page_names) -> dict:
    """Pick the winning page name, or report the mismatch.

    Returns ``{"page_name", "score"}`` on a match at or above
    ``MATCH_THRESHOLD``; otherwise ``{"error": "name_not_matched", "target",
    "candidates", "threshold"}`` with candidates sorted best-first.
    """
    target = str(target or "").strip()
    scored = [
        {"page_name": str(name or ""), "score": score_candidate(target, name)}
        for name in (page_names or [])
        if str(name or "").strip()
    ]
    scored = [c for c in scored if c["score"] > 0]
    scored.sort(key=lambda c: c["score"], reverse=True)
    # One candidate per page: six ads from the same page used to fill six of
    # the ten diagnostic slots. Sorted best-first, so the first hit per page
    # is the best-scoring one.
    seen_pages = set()
    unique = []
    for candidate in scored:
        page = normalize(candidate["page_name"])
        if page not in seen_pages:
            seen_pages.add(page)
            unique.append(candidate)
    scored = unique

    if scored and scored[0]["score"] >= MATCH_THRESHOLD:
        return {"page_name": scored[0]["page_name"], "score": scored[0]["score"]}

    return {
        "error": "name_not_matched",
        "target": target,
        "candidates": scored[:MAX_CANDIDATES],
        "threshold": MATCH_THRESHOLD,
    }


def filter_ads(ads, target):
    """Split ads by advertiser: ``(resolution, ads_on_winning_page)``.

    Ads are matched on the *normalized* page name, not the raw string: the
    library renders one page as ``K.F.C.``, ``KFC`` or `` kfc ``, and a raw
    equality check dropped every variant but the winner's spelling.
    """
    ads = list(ads or [])
    resolution = resolve_advertiser(target, [ad.get("page_name") for ad in ads])
    if "error" in resolution:
        return resolution, []
    winner = normalize(resolution["page_name"])
    kept = [ad for ad in ads if normalize(ad.get("page_name")) == winner]
    return resolution, kept
