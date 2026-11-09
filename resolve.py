"""Advertiser name resolution: score a page name against a target brand.

Ported from ``ad_intel.resolve`` (marketing-engineering), but name rungs only:
B has no ``page_id`` or handle, so A's 1.00 / 0.90 / 0.88 plateaus are out of
scope and its 0.70 rung (handle containment) has no analogue here. What is
kept is A's name ladder and its threshold:

* ``0.85`` normalized name — ``re.sub(r"[^a-z0-9]", "", name)`` on both sides
* ``0.80`` exact name, including a page that differs only by a trailing
  country qualifier (``Burger King Arabia`` == ``Burger King``). Qualifiers
  are matched against the full ISO-3166-1 table plus a small alias table of
  endonyms (``Deutschland``, ``Masr``, ``Brasil``, ``Türkiye``), and multi-word
  names (``United Arab Emirates``, ``South Africa``) are peeled as whole
  phrases so no country words are left glued to the brand. A page may only
  *add* a qualifier: when the target's own trailing country word is not kept
  by the page (``Air France`` vs ``Air Canada``), the core rungs are skipped
  and the pair falls to the substring rung — otherwise both cores collapse to
  the generic word ``air`` and a different airline passes at 0.80.
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
wrong-market PASS). A brand whose own name ends in a country word (``Little
Italy``, ``Air New Zealand``, ``Bank of Georgia``) is exempt: when every
qualifier the page names is one the target already carries, it is brand text,
not a market claim, and the page stays eligible.

Pure stdlib, pure functions over dicts.
"""

import re
import unicodedata

MATCH_THRESHOLD = 0.80

_NON_ALNUM = re.compile(r"[^a-z0-9]")

_WORD = re.compile(r"[^\W_]+", re.UNICODE)

#: ISO-3166-1 country names -> the market code the tool's ``country``
#: argument uses. Stdlib ships no ISO table, so this is written out; it is the
#: published ISO-3166-1 alpha-2 list, all 249 officially assigned countries.
#: Keys are already folded to lowercase ASCII words — the form
#: ``_fold_words`` produces — so a page's trailing words compare by plain
#: string equality. Long official forms ("United Kingdom of Great Britain and
#: Northern Ireland", "Korea, Republic of") are shortened to the name a page
#: prints; the short forms live here or in ``_COUNTRY_ALIASES``.
_ISO_COUNTRY_NAMES = {
    "afghanistan": "AF",
    "aland islands": "AX",
    "albania": "AL",
    "algeria": "DZ",
    "american samoa": "AS",
    "andorra": "AD",
    "angola": "AO",
    "anguilla": "AI",
    "antarctica": "AQ",
    "antigua and barbuda": "AG",
    "argentina": "AR",
    "armenia": "AM",
    "aruba": "AW",
    "australia": "AU",
    "austria": "AT",
    "azerbaijan": "AZ",
    "bahamas": "BS",
    "bahrain": "BH",
    "bangladesh": "BD",
    "barbados": "BB",
    "belarus": "BY",
    "belgium": "BE",
    "belize": "BZ",
    "benin": "BJ",
    "bermuda": "BM",
    "bhutan": "BT",
    "bolivia": "BO",
    "bonaire sint eustatius and saba": "BQ",
    "bosnia and herzegovina": "BA",
    "botswana": "BW",
    "bouvet island": "BV",
    "brazil": "BR",
    "british indian ocean territory": "IO",
    "british virgin islands": "VG",
    "brunei darussalam": "BN",
    "bulgaria": "BG",
    "burkina faso": "BF",
    "burundi": "BI",
    "cabo verde": "CV",
    "cambodia": "KH",
    "cameroon": "CM",
    "canada": "CA",
    "cayman islands": "KY",
    "central african republic": "CF",
    "chad": "TD",
    "chile": "CL",
    "china": "CN",
    "christmas island": "CX",
    "cocos keeling islands": "CC",
    "colombia": "CO",
    "comoros": "KM",
    "congo": "CG",
    "cook islands": "CK",
    "costa rica": "CR",
    "cote d ivoire": "CI",
    "croatia": "HR",
    "cuba": "CU",
    "curacao": "CW",
    "cyprus": "CY",
    "czechia": "CZ",
    "democratic republic of the congo": "CD",
    "denmark": "DK",
    "djibouti": "DJ",
    "dominica": "DM",
    "dominican republic": "DO",
    "ecuador": "EC",
    "egypt": "EG",
    "el salvador": "SV",
    "equatorial guinea": "GQ",
    "eritrea": "ER",
    "estonia": "EE",
    "eswatini": "SZ",
    "ethiopia": "ET",
    "falkland islands": "FK",
    "faroe islands": "FO",
    "fiji": "FJ",
    "finland": "FI",
    "france": "FR",
    "french guiana": "GF",
    "french polynesia": "PF",
    "french southern territories": "TF",
    "gabon": "GA",
    "gambia": "GM",
    "georgia": "GE",
    "germany": "DE",
    "ghana": "GH",
    "gibraltar": "GI",
    "greece": "GR",
    "greenland": "GL",
    "grenada": "GD",
    "guadeloupe": "GP",
    "guam": "GU",
    "guatemala": "GT",
    "guernsey": "GG",
    "guinea": "GN",
    "guinea bissau": "GW",
    "guyana": "GY",
    "haiti": "HT",
    "heard island and mcdonald islands": "HM",
    "holy see": "VA",
    "honduras": "HN",
    "hong kong": "HK",
    "hungary": "HU",
    "iceland": "IS",
    "india": "IN",
    "indonesia": "ID",
    "iran": "IR",
    "iraq": "IQ",
    "ireland": "IE",
    "isle of man": "IM",
    "israel": "IL",
    "italy": "IT",
    "jamaica": "JM",
    "japan": "JP",
    "jersey": "JE",
    "jordan": "JO",
    "kazakhstan": "KZ",
    "kenya": "KE",
    "kiribati": "KI",
    "kuwait": "KW",
    "kyrgyzstan": "KG",
    "laos": "LA",
    "latvia": "LV",
    "lebanon": "LB",
    "lesotho": "LS",
    "liberia": "LR",
    "libya": "LY",
    "liechtenstein": "LI",
    "lithuania": "LT",
    "luxembourg": "LU",
    "macao": "MO",
    "madagascar": "MG",
    "malawi": "MW",
    "malaysia": "MY",
    "maldives": "MV",
    "mali": "ML",
    "malta": "MT",
    "marshall islands": "MH",
    "martinique": "MQ",
    "mauritania": "MR",
    "mauritius": "MU",
    "mayotte": "YT",
    "mexico": "MX",
    "micronesia": "FM",
    "moldova": "MD",
    "monaco": "MC",
    "mongolia": "MN",
    "montenegro": "ME",
    "montserrat": "MS",
    "morocco": "MA",
    "mozambique": "MZ",
    "myanmar": "MM",
    "namibia": "NA",
    "nauru": "NR",
    "nepal": "NP",
    "netherlands": "NL",
    "new caledonia": "NC",
    "new zealand": "NZ",
    "nicaragua": "NI",
    "niger": "NE",
    "nigeria": "NG",
    "niue": "NU",
    "norfolk island": "NF",
    "north korea": "KP",
    "north macedonia": "MK",
    "northern mariana islands": "MP",
    "norway": "NO",
    "oman": "OM",
    "pakistan": "PK",
    "palau": "PW",
    "palestine": "PS",
    "panama": "PA",
    "papua new guinea": "PG",
    "paraguay": "PY",
    "peru": "PE",
    "philippines": "PH",
    "pitcairn": "PN",
    "poland": "PL",
    "portugal": "PT",
    "puerto rico": "PR",
    "qatar": "QA",
    "reunion": "RE",
    "romania": "RO",
    "russian federation": "RU",
    "rwanda": "RW",
    "saint barthelemy": "BL",
    "saint helena": "SH",
    "saint kitts and nevis": "KN",
    "saint lucia": "LC",
    "saint martin": "MF",
    "saint pierre and miquelon": "PM",
    "saint vincent and the grenadines": "VC",
    "samoa": "WS",
    "san marino": "SM",
    "sao tome and principe": "ST",
    "saudi arabia": "SA",
    "senegal": "SN",
    "serbia": "RS",
    "seychelles": "SC",
    "sierra leone": "SL",
    "singapore": "SG",
    "sint maarten": "SX",
    "slovakia": "SK",
    "slovenia": "SI",
    "solomon islands": "SB",
    "somalia": "SO",
    "south africa": "ZA",
    "south georgia and the south sandwich islands": "GS",
    "south korea": "KR",
    "south sudan": "SS",
    "spain": "ES",
    "sri lanka": "LK",
    "sudan": "SD",
    "suriname": "SR",
    "svalbard and jan mayen": "SJ",
    "sweden": "SE",
    "switzerland": "CH",
    "syrian arab republic": "SY",
    "taiwan": "TW",
    "tajikistan": "TJ",
    "tanzania": "TZ",
    "thailand": "TH",
    "timor leste": "TL",
    "togo": "TG",
    "tokelau": "TK",
    "tonga": "TO",
    "trinidad and tobago": "TT",
    "tunisia": "TN",
    "turkiye": "TR",
    "turkmenistan": "TM",
    "turks and caicos islands": "TC",
    "tuvalu": "TV",
    "uganda": "UG",
    "ukraine": "UA",
    "united arab emirates": "AE",
    "united kingdom of great britain and northern ireland": "GB",
    "united states minor outlying islands": "UM",
    "united states of america": "US",
    "uruguay": "UY",
    "us virgin islands": "VI",
    "uzbekistan": "UZ",
    "vanuatu": "VU",
    "venezuela": "VE",
    "viet nam": "VN",
    "wallis and futuna": "WF",
    "western sahara": "EH",
    "yemen": "YE",
    "zambia": "ZM",
    "zimbabwe": "ZW",
}

#: Endonyms, local spellings and the short forms pages actually print that
#: ISO's official name does not. Every entry maps to the canonical market its
#: ISO name already carries — this table adds no new markets, only the words a
#: page name may end with. Kept separate from the ISO table so coverage stays
#: auditable (``len(_ISO_COUNTRY_NAMES)`` is the country count).
_COUNTRY_ALIASES = {
    # Arabic / local names for existing markets
    "masr": "EG", "misr": "EG",
    # Europe, in the language of the page
    "deutschland": "DE", "osterreich": "AT", "schweiz": "CH", "suisse": "CH",
    "svizzera": "CH", "nederland": "NL", "holland": "NL", "belgie": "BE",
    "belgique": "BE", "polska": "PL", "sverige": "SE", "danmark": "DK",
    "norge": "NO", "suomi": "FI", "ceska republika": "CZ", "hellas": "GR",
    "italia": "IT", "espana": "ES", "magyarorszag": "HU",
    # Americas / Asia-Pacific, in the language of the page
    "brasil": "BR", "mexico": "MX", "pilipinas": "PH", "vietnam": "VN",
    "burma": "MM", "swaziland": "SZ", "macedonia": "MK", "russia": "RU",
    "syria": "SY", "cape verde": "CV", "ivory coast": "CI", "brunei": "BN",
    "vatican": "VA", "vatican city": "VA", "macau": "MO", "korea": "KR",
    # Short forms of long official ISO names
    "united states": "US", "usa": "US", "uk": "GB", "uae": "AE", "ksa": "SA",
    "united kingdom": "GB", "great britain": "GB", "britain": "GB",
}

#: Legacy short-form qualifiers, kept verbatim: the Gulf matrix's behaviour is
#: pinned to these exact pairs (``arabia`` is not here — it names a region, see
#: below). ``united``/``kingdom`` are spelled out because neither is a country
#: on its own; the full phrase ``united kingdom`` is in ``_COUNTRY_ALIASES``.
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

#: Every qualifier that names one market, longest-match first: the ISO names,
#: the aliases, and the legacy short forms (spread last, so the Gulf table's
#: exact values always win). ``arabia`` is deliberately absent — it is not a
#: country and stays in ``_REGIONAL_MARKET_TOKENS``, which is consulted only
#: after this table misses.
_MARKET_BY_PHRASE = {
    **_ISO_COUNTRY_NAMES,
    **_COUNTRY_ALIASES,
    **_MARKET_BY_TOKEN,
}
#: An ISO alpha-2 code is itself a qualifier: pages print ``KFC SA``.
_MARKET_BY_PHRASE.update(
    {code.lower(): code for code in _ISO_COUNTRY_NAMES.values()}
)

#: Alpha-2 codes that are also everyday English words or ubiquitous English
#: abbreviations (``me``, ``in``, ``it``, ``no``, ``us``, ``by``, ``tv``,
#: ``id``, ``ie``...). ``_fold_words`` lowercases, so without a guard a page
#: named ``Burger King me`` would peel ``me`` -> ME (Montenegro) and ``Burger
#: King us`` would peel ``us`` -> US, vetoing the page for every other market.
#: Codes are matched case-sensitively instead: only an all-caps token
#: (``Burger King ME``, ``KFC IN``) is the ISO code; lowercase and title-case
#: occurrences are prose and are left in the brand name.
#:
#: Derived by intersecting the 249 ISO alpha-2 codes with the two-letter
#: English words (and the few two-letter abbreviations a page prints as prose:
#: ``tv``, ``id``, ``ie``, ``io``, ``ai``, ``eg``, ``ms``, ``pm``). Every code
#: below is an assigned ISO code, so each still peels in capitals. Adding a
#: code here only *narrows* peeling, so the list is kept generous: a missing
#: entry is a false market veto, an extra one costs only an uppercase peel.
_AMBIGUOUS_TWO_LETTER_CODES = frozenset({
    # everyday words
    "ad", "am", "as", "at", "be", "by", "do", "in", "is", "it", "la", "ma",
    "me", "my", "ne", "no", "pa", "so", "to", "us", "ye",
    # everyday abbreviations / common two-letter tokens
    "ai", "eg", "id", "ie", "io", "ms", "pm", "tv",
})

#: Single words that may be peeled on their own. Multi-word names ("Saudi
#: Arabia", "United Arab Emirates") are peeled as whole phrases by
#: ``_peel_trailing``; their component words are not qualifiers by
#: themselves, so they stay out of this set.
_COUNTRY_TOKENS = frozenset(
    key
    for key in (*_MARKET_BY_PHRASE, *_REGIONAL_MARKET_TOKENS)
    if " " not in key
)

_PHRASE_KEYS = frozenset(_MARKET_BY_PHRASE) | frozenset(_REGIONAL_MARKET_TOKENS)
_MAX_PHRASE_WORDS = max(len(key.split()) for key in _PHRASE_KEYS)



def _fold_words(text) -> list[str]:
    """Split into lowercase words with accents folded, punctuation dropped.

    ``"Côte d'Ivoire"`` -> ``["cote", "d", "ivoire"]``, the same form the
    country tables are keyed on. NFKD + combining-mark removal is why
    ``España`` and ``Espana`` hit the same entry.
    """
    decomposed = unicodedata.normalize("NFKD", str(text or "").lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return [word for word in _WORD.findall(stripped) if word]


def _case_words(text) -> list[str]:
    """Same split as ``_fold_words`` but keeping each word's original case.

    Used only to tell an ISO code (``ME``) from the English word that shares
    its letters (``me``). Word count and order match ``_fold_words``.
    """
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return [word for word in _WORD.findall(stripped) if word]


def _peel_trailing(name) -> tuple[list[str], list[str]]:
    """Peel trailing country qualifiers, longest phrase first.

    Returns the remaining words and the peeled phrases. Longest-match matters
    for multi-word names: ``"Burger King United Arab Emirates"`` must peel
    ``"united arab emirates"`` as one phrase, not ``"emirates"`` alone (which
    would leave ``"united arab"`` glued to the brand and drop the score to the
    0.60 substring rung). One word is always left: a name that is nothing but
    qualifiers is not emptied.

    A two-letter code that is also an English word (``me``, ``in``, ``it``)
    peels only when the page prints it in capitals; see
    ``_AMBIGUOUS_TWO_LETTER_CODES``.
    """
    tokens = _fold_words(name)
    raw = _case_words(name)
    if len(raw) != len(tokens):
        raw = []  # alignment lost (defensive): never treat a code as uppercase
    peeled = []
    while len(tokens) > 1:
        limit = min(_MAX_PHRASE_WORDS, len(tokens) - 1)
        for size in range(limit, 0, -1):
            phrase = " ".join(tokens[-size:])
            if phrase not in _PHRASE_KEYS:
                continue
            if phrase in _AMBIGUOUS_TWO_LETTER_CODES and not (
                raw and all(word.isupper() for word in raw[-size:])
            ):
                continue
            peeled.append(phrase)
            del tokens[-size:]
            break
        else:
            break
    return tokens, peeled


def _strip_trailing_countries(name) -> tuple[str, bool]:
    """Drop trailing country-qualifier phrases, returning spaced words.

    ``"Burger King Arabia"`` -> ``("burger king", True)``;
    ``"Pizza Hut Saudi Arabia"`` -> ``("pizza hut", True)``;
    ``"Pizza Hut United Arab Emirates"`` -> ``("pizza hut", True)``. A name
    that is nothing but qualifiers is left intact so stripping can never
    empty it.
    """
    tokens, peeled = _peel_trailing(name)
    return " ".join(tokens), bool(peeled)


def _trailing_markets(name) -> frozenset[str]:
    """Market codes named by a page's trailing country qualifier.

    ``"Burger King Malaysia"`` -> ``{"MY"}``; ``"Pizza Hut KSA"`` -> ``{"SA"}``;
    ``"Burger King Arabia"`` -> the GCC set it regionalises to; a page with no
    qualifier -> the empty set. Same trailing-only peeling as
    ``_strip_trailing_countries``, but it reports *which* market was named so a
    candidate can be compared with the requested one.

    A specific country outranks a regional word: ``"Burger King Saudi Arabia"``
    peels the phrase ``saudi arabia``, which names SA, instead of widening to
    the Gulf the bare token ``arabia`` spans.
    """
    _, peeled = _peel_trailing(name)
    specific = set()
    regional = set()
    for phrase in peeled:
        code = _MARKET_BY_PHRASE.get(phrase)
        if code:
            specific.add(code)
        else:
            regional |= _REGIONAL_MARKET_TOKENS.get(phrase, frozenset())
    return frozenset(specific or regional)


def _is_brand_qualifier(page_name, target) -> bool:
    """True when the page's trailing qualifier is *inside* the brand name.

    ``Little Italy``, ``Air New Zealand`` and ``Bank of Georgia`` end in a
    country word that is part of the brand, not a market claim. The page is
    the brand's own page, so the qualifier must neither veto it nor count as
    a market match against the requested one.

    The test is containment, not equality: every market the page names must
    already be named by the target. A page carrying an *extra* qualifier
    (``Air New Zealand Australia``) still makes a claim the brand does not, so
    it is not exempt.
    """
    if not target:
        return False
    page_markets = _trailing_markets(page_name)
    if not page_markets:
        return False
    target_markets = _trailing_markets(target)
    return bool(target_markets) and page_markets <= target_markets


def _identity_rank(target, page_name, market=None) -> tuple[int, ...]:
    """Tie-breakers applied *after* score.

    Both components are higher-is-better and only decide between candidates
    that already scored the same; the numeric ladder (0.80 / 0.85 / 0.60) is
    untouched.

    * market — ``2`` when the page's country qualifier is the requested
      market, ``1`` when the page names no country or only a qualifier that
      the brand name itself carries (nothing contradicts the request), ``0``
      when it names a different one. Only present when the caller supplies a
      market: without one there is nothing to compare.
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
    elif _is_brand_qualifier(page_name, target):
        matched = 1
    else:
        matched = 0
    return (matched, exact)


def _names_other_market(page_name, market, target=None) -> bool:
    """True when the page explicitly qualifies a market other than ``market``.

    A page with *no* qualifier is global and acceptable for any requested
    market; only an explicit contradiction is vetoed. ``market`` absent means
    the caller does not know the market, so nothing can contradict it.

    ``target`` matters for brands whose name ends in a country word: when the
    page's trailing qualifier is one the target itself carries, it is part of
    the brand (``Little Italy`` for a US query) and the page is the brand's
    own, not a wrong-market page. See ``_is_brand_qualifier``.
    """
    wanted = str(market or "").strip().upper()
    if not wanted:
        return False
    markets = _trailing_markets(page_name)
    if not markets or wanted in markets:
        return False
    return not _is_brand_qualifier(page_name, target)



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


def _qualifiers_preserved(target, page_name) -> bool:
    """True when the page may stand for the *target*'s trailing qualifiers.

    A brand may end in a country word (``Air France``, ``Air New Zealand``,
    ``Little Italy``). Comparing peeled cores alone is unsafe: ``Air France``
    peels to the generic word ``air``, so ``Air Canada`` and ``Air India``
    matched it at 0.80 — a false PASS on a different airline.

    The comparison is between *market codes*, never phrase strings, so the same
    market spelled differently is preserved: ``Pizza Hut KSA`` names SA for
    ``Pizza Hut Saudi Arabia``; ``KFC United Arab Emirates`` names AE for
    ``KFC UAE``; ``McDonald's USA`` names US for ``McDonald's United States``;
    ``KFC Masr`` names EG for ``KFC Egypt``. Two different markets still fail:
    ``Air France`` (FR) against ``Air Canada`` (CA) is not preserved, because
    CA does not contain FR.

    A page with *no* trailing qualifier is the global page and is preserved
    for any target: the user wrote the market into the advertiser string
    (``KFC Saudi Arabia``) and the bare brand page (``KFC``) is the right
    resolution, not a dropped qualifier. Otherwise the target's markets must
    be a subset of the page's, so the page may add a market
    (``Air New Zealand Australia`` for ``Air New Zealand``) but never replace
    one.

    The mirror case — the page drops the target's qualifier
    (``Air France Canada`` -> ``Air France``) — is preserved too, but only
    when the page is the target *minus trailing words*: its words must be a
    strict prefix of the target's. That is the brand page, not a different
    market; ``Air France Canada`` against ``Air Canada`` is not a prefix and
    stays unpreserved.
    """
    _, target_peeled = _peel_trailing(target)
    if not target_peeled:
        return True
    page_markets = _trailing_markets(page_name)
    if not page_markets:
        return True
    if _trailing_markets(target) <= page_markets:
        return True
    page_tokens = _fold_words(page_name)
    target_tokens = _fold_words(target)
    return (
        bool(page_tokens)
        and len(page_tokens) < len(target_tokens)
        and target_tokens[: len(page_tokens)] == page_tokens
    )


def score_candidate(target, page_name) -> float:
    """Score how well ``page_name`` matches the ``target`` brand name.

    The 0.80 / 0.85 rungs compare *peeled cores*, which is only safe when the
    page preserves the qualifiers the target itself carries (see
    ``_qualifiers_preserved``). A page that swaps them (``Air Canada`` for
    ``Air France``) falls through to the substring rung and scores 0.0, so the
    three cross-airline false PASSes (``Air France``/``Air Canada``,
    ``Air France``/``Air India``, ``Air New Zealand``/``Air China``) are
    truthful misses.
    """
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
    # page for a brand is routinely named "<Brand> <Country>". Peel the
    # original casing, not ``raw_name``: a two-letter code is only a qualifier
    # in capitals (``KFC IT``), and lowercasing first would erase that.
    target_core, target_stripped = _strip_trailing_countries(str(target or "").strip())
    name_core, name_stripped = _strip_trailing_countries(str(page_name or "").strip())
    # Core equality is only evidence of the same brand when no country word
    # the target carries was swapped out. Without this, ``Air France`` -> core
    # ``air`` equalled ``Air Canada`` -> core ``air`` at 0.80.
    comparable = _qualifiers_preserved(target, page_name)
    if (target_stripped or name_stripped) and comparable and target_core == name_core:
        return 0.80
    if comparable and normalize(target_core) == normalize(name_core):
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

    The one exception is a qualifier that is part of the *brand*: when the page
    names only markets the target itself ends with (``Little Italy`` for US,
    ``Air New Zealand`` for US), the words are brand text and the page stays
    eligible. A page that adds a qualifier the brand does not carry
    (``Air New Zealand Australia``) still names another market and is vetoed.

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
        if wanted and _names_other_market(name, market, target):
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
