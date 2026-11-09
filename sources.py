"""Meta Ad Library URL building and markdown parsing.

The ad library is scraped by rendering the public page to markdown and parsing
that text. Cards are separated by ``* * *``; a complete card carries a page
label plus ``**Sponsored**`` and a status block (``Active``/``Inactive``,
``Library ID: <digits>``, date range). Captures can be truncated at a card
boundary, leaving an id-less header or a header-less status block, so the
parser pairs those leftovers instead of dropping them.

No network code lives here: fetching is delegated to the host's
``web_extract`` tool by :func:`fetch_ads`.
"""

from __future__ import annotations

import json
import re
import time

_LIBRARY_BASE = "https://www.facebook.com/ads/library/"

# The market code is interpolated into the URL; the tool layer validates it
# too, but build_url is public and is called directly by fetch_ads.
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

# The ad-library page renders to ~50k chars of markdown (BMW: 58,344), and the
# host's default 15k truncation silently drops most cards. Budget generously:
# a render that fills the whole budget comes back as a clipped prefix.
_CHAR_LIMIT = 120_000

# The host clips oversized pages head+tail and appends a footer (tools/
# web_tools_truncate.py): the middle is dropped, so any of these substrings in
# the returned text means cards may be missing regardless of char count.
_TRUNCATION_MARKERS = ("[TRUNCATED]", "middle omitted")

#: What ``complete`` in the fetch meta actually measures: whether *the rendered
#: page* came back unclipped. It never means Meta's whole result set was
#: retrieved — there is no pagination, so even ``complete: True`` is only the
#: top-N window the public render showed. Surfaced in the meta dict as
#: ``complete_scope`` so a machine reader cannot mistake the boolean for
#: "all results obtained".
COMPLETENESS_SCOPE = "rendered_window"

#: Fresh fetch attempts per call. The first is on the plain URL; the rest are
#: cache-busted because the host replays a cached extraction byte-for-byte for
#: the same URL. Four attempts left a contested phase failing ~29% of the
#: time at p(success|fresh) = 0.34 (evals/d3-shell-rootcause.md); six brings
#: that to ~8%, the doc's recommended budget.
_MAX_ATTEMPTS = 6

#: Wall-clock ceiling for the whole retry loop, so a pathological transport
#: cannot stretch one phase past a minute (its worst case is ~50 s of renders).
_FETCH_DEADLINE_S = 60.0

#: Transport errors (not parse failures) are retried this many times.
_TRANSPORT_RETRIES = 1

#: Canonical URLs that already returned a pre-hydration shell in this process.
#: The host caches extractions per URL, so the next fetch for such a URL must
#: start cache-busted: attempt 1 on the plain URL would just replay the shell
#: cached during an earlier phase (0.01 s, zero information).
_dead_render_urls: set[str] = set()


def reset_dead_render_cache() -> None:
    """Forget the in-process shell URL cache (tests, and a manual reset)."""
    _dead_render_urls.clear()


#: A render with no card markers is a genuinely empty listing ONLY when it
#: actually says so. The ad-library empty state reads like "No ads match your
#: search"; a pre-hydration shell (nav + country list, ~2-5k chars, no empty-
#: state wording) is a fetch failure and must raise, never return [].
_EMPTY_STATE_RE = re.compile(
    r"no ads (match|found)|we didn't find|we couldn.?t find|no results? (found|match)",
    re.IGNORECASE,
)

#: Typed reasons for a render that carried no usable listing. ``shell`` is the
#: pre-hydration ad-library chrome (nav + country picker + footer, no results
#: grid); ``blocked`` is a consent/login/rate-limit wall; ``markup_changed`` is
#: anything else — the page rendered but the card markup no longer parses.
DEAD_RENDER_SHELL = "shell"
DEAD_RENDER_BLOCKED = "blocked"
DEAD_RENDER_MARKUP = "markup_changed"

# A wall the library shows instead of results. Deliberately phrase-level: the
# normal shell footer links to a "Cookies" policy page, so a bare word like
# "cookie" or "login" would misclassify a healthy render.
_BLOCKED_RE = re.compile(
    r"log ?in to continue|sign ?in to continue|you must log ?in"
    r"|confirm your identity|unusual activity|account (?:is )?temporarily locked"
    r"|too many requests|rate limit|temporarily blocked|access denied"
    r"|request (?:was )?blocked|accept all cookies|allow all cookies",
    re.IGNORECASE,
)

#: The ad-library SPA chrome that is present *before* the results grid paints.
#: Any card marker at all wins over these (a real render carries both).
_SHELL_NAV_MARKERS = ("Ad Library Report", "Ad Library API", "Branded Content")
_SHELL_CHROME_MARKERS = (
    "select country",
    "search by keyword or advertiser",
    "ad category",
)
_SHELL_FOOTER_MARKERS = (
    "metastatus.com/ads-transparency",
    "about ads and data use",
    "system status",
)
_CARD_EVIDENCE_RE = re.compile(r"\*\*Sponsored\*\*|Library ID:\s*\d")


def classify_dead_render(md: str) -> str | None:
    """Type a render that carries no listing, or ``None`` when it is usable.

    Returns one of :data:`DEAD_RENDER_SHELL` / :data:`DEAD_RENDER_BLOCKED` /
    :data:`DEAD_RENDER_MARKUP`, or ``None`` for content that carries card
    markers or the genuine empty-state wording. Header-only classification —
    the actionability decision (retry vs. fail) stays with the caller.
    """
    if not md or not isinstance(md, str) or not md.strip():
        return None
    # A card marker means the results grid painted; whatever fails after that
    # is a parse/markup problem, not a dead render.
    if _CARD_EVIDENCE_RE.search(md):
        return None
    if _BLOCKED_RE.search(md):
        return DEAD_RENDER_BLOCKED
    if _EMPTY_STATE_RE.search(md):
        return None
    lowered = md.lower()
    has_nav = any(marker in md for marker in _SHELL_NAV_MARKERS)
    has_picker = any(marker in lowered for marker in _SHELL_CHROME_MARKERS)
    has_footer = any(marker in lowered for marker in _SHELL_FOOTER_MARKERS)
    if has_nav and (has_picker or has_footer):
        return DEAD_RENDER_SHELL
    return DEAD_RENDER_MARKUP


class FetchError(RuntimeError):
    """The host fetch failed or returned no usable content."""


class ParseError(Exception):
    """The page rendered content that looks like ads but parsed to none.

    Raised instead of returning ``[]`` so a markup change is never mistaken
    for "this advertiser has no ads".

    ``cards_seen`` is the number of card markers found in the render.
    ``reason`` types the failure (see the ``DEAD_RENDER_*`` constants);
    ``dead_render`` is the same value, named for the meta/error field.
    """

    def __init__(
        self,
        message: str = "no cards parsed",
        cards_seen: int = 0,
        reason: str = DEAD_RENDER_MARKUP,
    ):
        super().__init__(message)
        self.cards_seen = cards_seen
        self.reason = reason
        self.dead_render = reason

    def __str__(self) -> str:
        message = super().__str__()
        # Only a pre-results render gets the typed prefix; a markup-change
        # message keeps its original wording so existing error strings still
        # match for callers that only stringify the exception.
        if self.reason in (DEAD_RENDER_SHELL, DEAD_RENDER_BLOCKED):
            return f"dead_render: {self.reason}: {message}"
        return message


_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"
)


def _quote_plus(text: str) -> str:
    """Percent-encode like a query component, stdlib-free of network imports."""
    parts = []
    for byte in str(text).encode("utf-8"):
        char = chr(byte)
        if char in _UNRESERVED:
            parts.append(char)
        elif char == " ":
            parts.append("+")
        else:
            parts.append(f"%{byte:02X}")
    return "".join(parts)

_STATUS_RE = re.compile(r"^(Active|Inactive)$")
_LIBRARY_ID_RE = re.compile(r"^Library ID:\s*(\d+)$")

#: The ad marker. Renders carry the plain ``**Sponsored**`` label, but a
#: variant appends the payer inline: ``**Sponsored** • Paid for by **Page**``.
#: The card is otherwise identical, so the variant must be recognized as the
#: same marker or the whole card is dropped as unparsed.
_SPONSOR_MARKER_RE = re.compile(
    r"^\*\*Sponsored\*\*(?:\s*[•\u2022·]\s*Paid for by\b.*)?$"
)
_PAGE_LINK_URL_RE = re.compile(
    r"^\[([^\]]+)\]\((https://www\.facebook\.com/[^)\s]*)\)"
)
#: Creator-run cards are labelled with an Instagram profile instead of a
#: Facebook page: ``[handle](https://www.instagram.com/_u/<handle>)``, alone
#: or as the first name of a co-advertiser label. Only profile paths count;
#: ``/accounts/login``, ``/legal/terms`` and friends are page chrome.
_IG_PAGE_LINK_URL_RE = re.compile(
    r"^\[([^\]]+)\]\((https?://(?:www\.)?instagram\.com/"
    r"(?:_u/)?(?P<handle>[A-Za-z0-9._]+)/?)\)"
)
_IG_RESERVED_PATHS = frozenset(
    {
        "_u",
        "accounts",
        "api",
        "about",
        "developer",
        "directory",
        "emails",
        "explore",
        "help",
        "legal",
        "p",
        "privacy",
        "reel",
        "reels",
        "session",
        "stories",
        "tv",
    }
)
_NUMERIC_PAGE_RE = re.compile(r"facebook\.com/(\d+)(?:[/?#]|$)")
# profile.php?id=<digits> is the other way the library links a numeric page.
_PROFILE_PHP_PAGE_RE = re.compile(
    r"facebook\.com/profile\.php\?[^)\s#]*\bid=(\d+)"
)
_IMAGE_ALT_RE = re.compile(r"^!\[([^\]]*)\]\(")
_IMAGE_URL_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
_CTA_DEST_RE = re.compile(r"\]\((https?://[^)\s]+)\)")
_HELP_URL_RE = re.compile(r"^https?://(?:www\.)?facebook\.com/help/")
_DOMAIN_RE = re.compile(
    r"^[A-Z0-9][A-Z0-9-]*\.[A-Z][A-Z0-9.-]*$", re.IGNORECASE
)
_SAME_CREATIVE_RE = re.compile(
    r"\*\*(\d+)\s+ads?\*\*\s+use this creative and text"
)
_VIDEO_MARKER = "Sorry, we're having trouble playing this video."
_MULTIPLE_VERSIONS_MARKER = "This ad has multiple versions"
_DATE_RANGE_RE = re.compile(r"^(.+?)\s+-\s+(.+)$")
_STARTED_RE = re.compile(r"^Started running on\s+(.+)$")

_NOISE_LINES = {
    "",
    "\u200b",
    "Platforms",
    "EU transparency",
    "Open Dropdown",
    "See ad details",
    "See summary details",
    "See more",
    "Filters",
    "Sort",
    "Sort by",
    "Sorry, we're having trouble playing this video.",
    "This ad has multiple versions",
}

_NOISE_PREFIXES = (
    "**",  # "**4 ads** use this creative and text" and similar annotations
)

#: A line that is nothing but a markdown link, e.g. ``[Shop Now](https://…)``.
#: A trailing ``\`` is a wrap escape, not content. Only this shape is chrome:
#: a broader "contains ](" test erased copy that merely mentioned a link.
_LINK_LINE_RE = re.compile(r"^\[[^\]]*\]\([^)]*\)\\?$")

#: A markdown link inside a line of copy, stripped down to its label.
_INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

#: How many following non-blank lines may carry a wrapped CTA's ``](``
#: destination. Bounded so an unbalanced bracket in real copy ("As seen in
#: [Vogue") cannot swallow the rest of the creative.
_CTA_LOOKAHEAD = 3

# The library's page footer ("System status" plus links to its own policy
# pages) trails the last card in every render. Match the destinations, not the
# labels: the labels are localized, the URLs are not.
_PAGE_FOOTER_LINK_RE = re.compile(
    r"^-\s+\[[^\]]*\]\(https://www\.facebook\.com/"
    r"(?:ads/library/api/|ads/about/|privacy/center/|policies/)[^)]*\)\\{0,2}$"
)
_PAGE_FOOTER_STATUS_RE = re.compile(r"^System status\\{0,2}$")

# A bare box-drawing rule is only chrome as part of the host footer block; a
# creative may end with its own divider ("Copy line" over a rule).
_BOX_DIVIDER_RE = re.compile(r"^─{3,}\\{0,2}$")

# The host's head+tail truncation footer (tools/web_tools_truncate.py) appends
# a banner, a size summary and an absolute cache path — or, when the cache
# write fails, a sentence saying the full text could not be stored. The path
# changes on every fetch, so leaving it in creative_text makes unchanged ads
# look changed.
_HOST_FOOTER_RE = re.compile(
    r"^(?:"
    r"─{3,}\s*\[TRUNCATED\]\s*─{3,}"
    r"|Showing [\d,]+ chars \(head\) \+ [\d,]+ chars \(tail\) "
    r"of [\d,]+ total clean characters\.?"
    r"|Full text saved to: .+"
    r"|Full text could not be stored.*"
    r"|To read the omitted middle: read_file path=.*"
    r")\\{0,2}$"
)


def _is_footer_line(line: str) -> bool:
    """True when ``line`` is one of the host/page footer chrome lines."""
    return bool(
        _HOST_FOOTER_RE.match(line)
        or _PAGE_FOOTER_STATUS_RE.match(line)
        or _PAGE_FOOTER_LINK_RE.match(line)
    )


def _preceded_by_footer_block(kept: list[str]) -> bool:
    """True when the line above ``kept[-1]`` is part of a footer block."""
    index = len(kept) - 2
    while index >= 0 and not kept[index].strip("\\").strip():
        index -= 1
    return index >= 0 and _is_footer_line(kept[index])


def _strip_footers(kept: list[str]) -> list[str]:
    """Drop a trailing page/host footer from cleaned creative lines.

    Only trailing runs are removed, and only lines that are unambiguously
    chrome: the library's fixed policy links, its ``System status`` label, the
    host's truncation banner/summary/cache-path lines, the closing rule of
    that footer block, and the lone backslash wrap residue those lines leave
    behind. A bare rule or one of those URLs mid-copy is creative and is
    preserved.
    """
    while kept:
        line = kept[-1]
        if _is_footer_line(line):
            kept.pop()
            continue
        # The footer block's closing rule is chrome only when it closes one.
        if _BOX_DIVIDER_RE.match(line) and _preceded_by_footer_block(kept):
            kept.pop()
            continue
        # Wrapped markdown leaves a lone backslash between/after footer lines.
        if not line.strip("\\").strip():
            kept.pop()
            continue
        break
    return kept


def _strip_footer_blocks(kept: list[str]) -> list[str]:
    """Drop footer blocks *anywhere* in the cleaned creative lines.

    A capture can append the host head+tail footer (or the library's page
    footer) between two creative fragments — the footer is not always trailing
    the last card. Left in place, its per-fetch cache path makes unchanged
    creative look changed, so a footer block is removed wherever it appears,
    not just at the end.

    A block is chrome only when it is unambiguous: it carries a host footer
    line (banner, size summary, cache path), or it is a run of at least two
    page-footer lines (the ``System status`` label plus policy links). A lone
    policy-looking link or a mid-copy ``System status`` line stays creative.
    """
    out: list[str] = []
    index = 0
    while index < len(kept):
        line = kept[index]
        if not (_is_footer_line(line) or _BOX_DIVIDER_RE.match(line)):
            out.append(line)
            index += 1
            continue
        end = index
        while end < len(kept) and (
            _is_footer_line(kept[end]) or _BOX_DIVIDER_RE.match(kept[end])
        ):
            end += 1
        block = kept[index:end]
        host_block = any(_HOST_FOOTER_RE.match(item) for item in block)
        page_lines = sum(
            1 for item in block
            if _is_footer_line(item) and not _HOST_FOOTER_RE.match(item)
        )
        if host_block or page_lines >= 2:
            index = end
            continue
        out.extend(block)
        index = end
    return out


#: Filter vocabularies, mirroring the public library's own URL parameters.
ACTIVE_STATUSES = ("all", "active", "inactive")
MEDIA_TYPES = ("all", "image", "video")


def _choice(name: str, value, allowed: tuple[str, ...]) -> str:
    """Validate a filter value, raising ``ValueError`` with its tool error name.

    The message matches the tool-level error token
    (``invalid_active_status`` / ``invalid_media_type``) so a caller that just
    surfaces the exception still names the bad field.
    """
    text = value.strip() if isinstance(value, str) else ""
    if text not in allowed:
        raise ValueError(f"invalid_{name}")
    return text


def build_url(
    query: str,
    country: str = "US",
    active_status: str = "all",
    media_type: str = "all",
) -> str:
    """Public ad-library search URL for ``query``.

    ``active_status`` (``all``/``active``/``inactive``) and ``media_type``
    (``all``/``image``/``video``) are the library's own free query parameters:
    no key, token or third-party service is involved. ``country`` must be a
    two-letter uppercase market code. Invalid values raise ``ValueError``.
    """
    if not isinstance(country, str) or not _COUNTRY_RE.fullmatch(country):
        raise ValueError("invalid_country")
    active_status = _choice("active_status", active_status, ACTIVE_STATUSES)
    media_type = _choice("media_type", media_type, MEDIA_TYPES)
    return (
        f"{_LIBRARY_BASE}?active_status={active_status}&ad_type=all"
        f"&country={country}&q={_quote_plus(query)}&media_type={media_type}"
        f"&search_type=keyword_unordered"
    )


def _card_blocks(md: str) -> list[list[str]]:
    blocks: list[list[str]] = [[]]
    for line in md.splitlines():
        if line.strip() == "* * *":
            blocks.append([])
        else:
            blocks[-1].append(line.rstrip())
    return blocks


def _is_sponsor_marker(line: str) -> bool:
    """True for the card's ``**Sponsored**`` label, including the payer variant."""
    return bool(_SPONSOR_MARKER_RE.match(line.strip()))


def _sponsor_marker_count(lines: list[str]) -> int:
    """How many cards' worth of ad markers a block carries.

    One per card. Zero means the block is not a card body. Two or more means
    cards were concatenated without the ``* * *`` separator (a render seam),
    so only one of them can be parsed from that block and the rest are lost.
    """
    return sum(1 for line in lines if _is_sponsor_marker(line))


def _has_card_marker(lines: list[str]) -> bool:
    """A block that claims to be (part of) an ad card, whether or not it parses.

    Card markers, not separators, are the signal: a genuinely empty results
    page still has ``* * *`` chrome separators but no ``**Sponsored**`` or
    ``Library ID`` anywhere.

    A ``Library ID`` alone is a *status block* — the half of a card a capture
    boundary can split off — so it counts toward ``cards_seen`` here. It is
    not, however, an ad marker for unparsed accounting: see
    :func:`_sponsor_marker_count`.
    """
    for raw in lines:
        line = raw.strip()
        if _is_sponsor_marker(line) or line.startswith("Library ID:"):
            return True
    return False


def _status_index(lines: list[str]) -> int | None:
    """Index of the status line that starts a valid status block."""
    for i, line in enumerate(lines):
        if not _STATUS_RE.match(line.strip()):
            continue
        for nxt in lines[i + 1 : i + 4]:
            if not nxt.strip():
                continue
            if _LIBRARY_ID_RE.match(nxt.strip()):
                return i
            break
    return None


def _cta_continues(lines: list[str], start: int) -> bool:
    """True when the next few non-blank lines carry a link destination.

    The signal that a line starting with ``[`` is a wrapped CTA opener rather
    than copy with a bracket in it: somewhere just below, a line contains
    ``](``. Lookahead is bounded (see :data:`_CTA_LOOKAHEAD`) so a stray
    unbalanced bracket cannot swallow the rest of the creative.
    """
    seen = 0
    for raw in lines[start + 1 :]:
        if not raw.strip():
            continue
        if "](" in raw:
            return True
        seen += 1
        if seen >= _CTA_LOOKAHEAD:
            return False
    return False


def _clean_creative(lines: list[str]) -> str:
    kept: list[str] = []
    skipping_link_block = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if skipping_link_block:
            # A multi-line markdown link/CTA continues until the "](" line.
            if "](" in line:
                skipping_link_block = False
            continue
        if line.startswith("]("):
            # Destination half of a CTA whose ``[title`` opener is gone.
            continue
        if line.startswith("["):
            # Only link-shaped lines are chrome. Copy may legitimately start
            # with a bracket ("[NEW] 50% off today"), and dropping every such
            # line erased real creative text.
            if _LINK_LINE_RE.match(line):
                continue
            bare = line.rstrip("\\").strip()
            if "](" in line:
                if bare.endswith(")") and line.count("[") == line.count("]"):
                    # A link or a linked image (``[![](img)](dest)``): chrome.
                    continue
                if line.count("[") > line.count("]"):
                    # The wrap broke before the closing "]": the destination
                    # is on a later line.
                    skipping_link_block = True
                    continue
                # Copy that merely mentions a link stays copy, with the link
                # markup stripped.
                kept.append(_INLINE_LINK_RE.sub(r"\1", line))
                continue
            if line.endswith("\\"):
                # A wrapped first line of a multi-line CTA: "[Title \"
                # with the destination (and ``](``) on a later line.
                skipping_link_block = True
                continue
            if line.count("[") > line.count("]"):
                # An unclosed opener: the CTA title wraps onto later lines.
                # A wrapped render can end every line with ``\`` or with no
                # escape at all, so the escape is not the signal — the missing
                # ``]`` is. Confirm the paragraph really ends in a link;
                # otherwise the bracket is copy ("As seen in [Vogue").
                if _cta_continues(lines, i):
                    skipping_link_block = True
                    continue
                kept.append(line)
                continue
            # Not link-shaped: keep it as copy.
            kept.append(line)
            continue
        if (
            line in _NOISE_LINES
            or line.rstrip("\\").strip() in _NOISE_LINES
            or line.startswith(_NOISE_PREFIXES)
        ):
            # Wrapped markdown can leave a trailing ``\`` on a chrome line.
            continue
        if line.startswith("!["):
            continue
        kept.append(line)
    kept = _strip_footers(_strip_footer_blocks(kept))
    return "\n".join(kept).strip()


def _dates(lines: list[str], start: int) -> tuple[str, str]:
    """First/last seen strings from the lines following ``Library ID``."""
    for raw in lines[start + 1 : start + 6]:
        line = raw.strip()
        if not line:
            continue
        started = _STARTED_RE.match(line)
        if started:
            return started.group(1).strip(), ""
        rng = _DATE_RANGE_RE.match(line)
        if rng:
            return rng.group(1).strip(), rng.group(2).strip()
        if _STATUS_RE.match(line) or _LIBRARY_ID_RE.match(line):
            return "", ""
    return "", ""


def _ig_page_label(line: str) -> tuple[str, str] | None:
    """``(page_name, page_url)`` when ``line`` links an Instagram profile.

    The page name is the profile handle (the ``_u/`` path segment is not
    part of it), so a markdown-escaped label such as
    ``[livelonger\\_livehealthier]`` still yields the real handle.
    """
    match = _IG_PAGE_LINK_URL_RE.match(line)
    if not match:
        return None
    handle = match.group("handle")
    if handle.lower() in _IG_RESERVED_PATHS:
        return None
    return handle, match.group(2).strip()


def _page_label_before(lines: list[str], sponsored_idx: int) -> tuple[str, str]:
    """``(page_name, page_url)`` for the label above ``**Sponsored**``.

    The URL is the label's own link (``facebook.com/nike/``, a numeric
    profile id, or an Instagram profile), taken from the first link of a
    co-advertiser label such as ``[Noemimisma](…) with [Nike](…)``. When only
    an image alt text names the page, it is the name and the URL is ``""``.
    """
    for raw in reversed(lines[:sponsored_idx]):
        line = raw.strip()
        if not line:
            continue
        link = _PAGE_LINK_URL_RE.match(line)
        if link:
            return link.group(1).strip(), link.group(2).strip()
        instagram = _ig_page_label(line)
        if instagram:
            return instagram
        image = _IMAGE_ALT_RE.match(line)
        if image and image.group(1).strip():
            return image.group(1).strip(), ""
        if not _is_sponsor_marker(line):
            return "", ""
    return "", ""


def _numeric_page_id(page_url: str) -> str:
    """The digits in a numeric profile URL, else ``""``.

    Vanity handles (``facebook.com/nike/``) carry no page id in the public
    render, and inventing one would poison joins.
    """
    match = _NUMERIC_PAGE_RE.search(page_url or "")
    if match:
        return match.group(1)
    # profile.php?id=<digits> is the other numeric-page link shape.
    match = _PROFILE_PHP_PAGE_RE.search(page_url or "")
    return match.group(1) if match else ""


def _link_blocks(lines: list[str]) -> list[list[str]]:
    """Group multi-line markdown links (CTA cards) into whole blocks.

    A block starts at a line beginning with ``[`` and ends at the line that
    carries ``](`` (the destination), because the title/CTA text is wrapped
    across several ``\\\\``-terminated lines. Single-line links are blocks of
    one.
    """
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for raw in lines:
        line = raw.strip()
        complete = line.endswith(")") and "](" in line
        if current is not None:
            current.append(line)
            if complete:
                blocks.append(current)
                current = None
            continue
        if not line.startswith("["):
            continue
        if complete:
            blocks.append([line])
        else:
            current = [line]
    return blocks


def _cta_fields(block: list[str]) -> dict | None:
    """``link_url``/``link_title``/``cta_text`` from one CTA link block.

    Returns ``None`` for help-centre links: they are UI chrome ("Learn more"
    opens Meta's help page), not the advertiser's destination.
    """
    text = "\n".join(block)
    destinations = _CTA_DEST_RE.findall(text)
    if not destinations:
        return None
    dest = destinations[-1]
    if _HELP_URL_RE.match(dest):
        return None

    start = text.find("[")
    stop = text.rfind("](")
    if start < 0 or stop <= start:
        return None
    body = _IMAGE_URL_RE.sub(" ", text[start + 1 : stop])
    body = re.sub(r"\\+", "\n", body)

    segments: list[str] = []
    for part in body.split("\n"):
        value = part.strip().strip("\\").strip()
        if value and (not segments or segments[-1] != value):
            segments.append(value)
    cta_text = segments[-1] if segments else ""
    # The first segment is the display domain the card prints above the title
    # (``AD.DOUBLECLICK.NET``). It is Treg's ``link_caption``: the caption
    # shown, not the URL host (``bk.com`` can point at an ``app.link``
    # redirect), so it is surfaced rather than dropped — but kept out of the
    # title.
    link_caption = ""
    if segments and _DOMAIN_RE.match(segments[0]):
        link_caption = segments[0].rstrip("/")
    title_parts = [s for s in segments[:-1] if not _DOMAIN_RE.match(s)]
    return {
        "link_url": dest,
        "link_title": " ".join(title_parts),
        "cta_text": cta_text,
        "link_caption": link_caption,
    }


#: Treg's ``cta_type`` vocabulary, keyed by the lowercased CTA label the public
#: render prints. The labels come from Treg's own ``cta`` -> ``cta_type`` pairs
#: (``Order now`` -> ``ORDER_NOW``, ``Install now`` -> ``INSTALL_MOBILE_APP``,
#: ``Use app`` -> ``USE_MOBILE_APP``) plus the common labels from the fixture.
_CTA_TYPES = {
    "order now": "ORDER_NOW",
    "shop now": "SHOP_NOW",
    "learn more": "LEARN_MORE",
    "sign up": "SIGN_UP",
    "download": "DOWNLOAD",
    "get offer": "GET_OFFER",
    "install now": "INSTALL_MOBILE_APP",
    "use app": "USE_MOBILE_APP",
    "see details": "SEE_DETAILS",
    "book now": "BOOK_NOW",
    "buy now": "BUY_NOW",
    "contact us": "CONTACT_US",
    "apply now": "APPLY_NOW",
    "subscribe": "SUBSCRIBE",
    "message us": "MESSAGE_US",
    "send message": "SEND_MESSAGE",
}


def cta_type(text=None) -> str:
    """Upper-snake CTA type for a rendered CTA label.

    Known labels map to Treg's vocabulary; anything else is normalised to
    upper snake (``Visit Instagram profile`` -> ``VISIT_INSTAGRAM_PROFILE``)
    rather than guessed at or dropped. An absent label yields ``""``.
    """
    key = " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())
    if not key:
        return ""
    return _CTA_TYPES.get(key) or "_".join(key.split()).upper()


#: Display formats a stored payload may assert. Only the three the public
#: render can support are trusted: ``carousel`` and ``multi_images`` are
#: indistinguishable from ``dco`` in the render (see :func:`_display_format`),
#: so an untrusted payload claiming them would emit a fact the plugin cannot
#: verify. Such a claim is dropped to ``""`` rather than passed through.
_PAYLOAD_DISPLAY_FORMATS = ("image", "video", "dco")


def _display_format(images: list[str], has_video: bool) -> str:
    """Infer Treg's ``display_format`` from what the card rendered.

    Multiple rendered images (or an image mixed with video) is dynamic creative
    — Treg's dominant multi-creative value, ``dco`` (57 of its 59 multi-image
    ads). ``carousel`` cannot be told apart from ``dco`` in the public render,
    so it is never claimed. One image is ``image``; video without images is
    ``video``. No media signal yields ``""`` (unknown, not invented).
    """
    if has_video and images:
        return "dco"
    if len(images) > 1:
        return "dco"
    if images:
        return "image"
    if has_video:
        return "video"
    return ""


def _cards(ad: dict) -> list[dict]:
    """Per-card grouping in Treg's shape.

    A multi-image ad is one card per rendered image (Treg repeats the ad body,
    CTA and link on each card and varies only the image); a single-media ad is
    a one-element list so the shape never varies. No video file URL is ever
    invented: ``video`` stays ``None``.
    """
    images = ad.get("images") or []
    body = ad.get("creative_text") or ""
    cta = ad.get("cta_text") or ""
    link_url = ad.get("link_url") or ""
    title = ad.get("link_title") or ""
    image_list = images if len(images) > 1 else images[:1] or [None]
    return [
        {
            "body": body,
            "cta": cta,
            "image": image,
            "link_url": link_url,
            "title": title,
            "video": None,
        }
        for image in image_list
    ]


def _with_free_fields(ad: dict) -> dict:
    """Fill ``cta_type``/``display_format``/``cards`` from the parsed fields."""
    ad["cta_type"] = cta_type(ad.get("cta_text"))
    ad["display_format"] = _display_format(
        ad.get("images") or [], bool(ad.get("has_video"))
    )
    ad["cards"] = _cards(ad)
    ad.setdefault("link_caption", "")
    return ad


def _image_urls(lines: list[str]) -> list[str]:
    """Creative image URLs, excluding the 60x60 page profile picture."""
    urls: list[str] = []
    for raw in lines:
        for url in _IMAGE_URL_RE.findall(raw):
            if "60x60" in url:
                continue
            if url not in urls:
                urls.append(url)
    return urls


def _parse_block(lines: list[str]) -> dict | None:
    sponsored_idx = next(
        (i for i, line in enumerate(lines) if _is_sponsor_marker(line)),
        None,
    )
    status_idx = _status_index(lines)

    ad: dict = {}
    if status_idx is not None:
        status_line = lines[status_idx].strip()
        id_idx = -1
        for i in range(status_idx + 1, min(status_idx + 4, len(lines))):
            if _LIBRARY_ID_RE.match(lines[i].strip()):
                id_idx = i
                break
        if id_idx < 0:
            return None
        library_id = _LIBRARY_ID_RE.match(lines[id_idx].strip()).group(1)
        first_seen, last_seen = _dates(lines, id_idx)
        ad = {
            "id": library_id,
            "status": "active" if status_line == "Active" else "ended",
            "first_seen": first_seen,
            "last_seen": last_seen,
        }

    if sponsored_idx is not None:
        page_name, page_url = _page_label_before(lines, sponsored_idx)
        ad["page_name"] = page_name
        ad["page_url"] = page_url
        ad["page_id"] = _numeric_page_id(page_url)
        end = status_idx if status_idx is not None else len(lines)
        creative_lines = lines[sponsored_idx + 1 : end]
        ad["creative_text"] = _clean_creative(creative_lines)
        ad["images"] = _image_urls(creative_lines)
        ad["has_video"] = any(
            line.strip() == _VIDEO_MARKER for line in creative_lines
        )
        for block in _link_blocks(creative_lines):
            cta = _cta_fields(block)
            if cta:
                ad.update(cta)
                break

    if not ad:
        return None

    # Creative-grouping annotations sit in the status region of the card.
    same_creative = 0
    for raw in lines:
        match = _SAME_CREATIVE_RE.match(raw.strip())
        if match:
            same_creative = int(match.group(1))
            break
    ad["same_creative_count"] = same_creative
    ad["multiple_versions"] = any(
        line.strip() == _MULTIPLE_VERSIONS_MARKER for line in lines
    )
    return ad


def parse_library_markdown_with_meta(md: str) -> tuple[list[dict], dict]:
    """Parse a rendered results page, also reporting card-marker accounting.

    Returns ``(ads, {"cards_seen": int, "unparsed_cards": int})``.
    ``cards_seen`` is the number of blocks carrying a card marker
    (``**Sponsored**``, its payer variant, or ``Library ID``).
    ``unparsed_cards`` counts only marker-bearing blocks that produced no ad
    *and* carry the ad marker itself — a Sponsored header whose status block
    was cut off, or a card whose markup changed. A bare ``Library ID`` status
    block at a window edge is not counted: its header was never in the capture,
    so no card was lost. A block carrying more than one ad marker is a seam
    where cards were concatenated without a separator: only the first parses,
    so each extra marker adds one to ``unparsed_cards``. A capture that
    dropped a card must not be reported as a complete listing, so the caller
    folds ``unparsed_cards`` into its completeness decision.

    Raises :class:`ParseError` with the same contract as
    :func:`parse_library_markdown`.
    """
    if not md or not isinstance(md, str):
        return [], {"cards_seen": 0, "unparsed_cards": 0}
    blocks = _card_blocks(md)
    parsed_blocks = [(block, _parse_block(block)) for block in blocks]
    records = [rec for _, rec in parsed_blocks if rec]
    cards_seen = sum(1 for block in blocks if _has_card_marker(block))

    # Recover cards cut in two by a capture/separator boundary: a status block
    # with no page label picks up a page label with no status block. Complete
    # cards always consume their own label, so only leftovers pair here.
    orphans = [r for r in records if "id" not in r and r.get("page_name")]
    consumed_orphans: set[int] = set()
    for rec in records:
        if "id" in rec and not rec.get("page_name") and orphans:
            orphan = orphans.pop(0)
            consumed_orphans.add(id(orphan))
            rec["page_name"] = orphan["page_name"]
            rec["page_url"] = orphan.get("page_url", "")
            rec["page_id"] = orphan.get("page_id", "")
            # The creative lives on the header side of the split. Carry it
            # over rather than reporting the status-only half as a blank ad.
            for key in _CREATIVE_KEYS:
                if not rec.get(key) and orphan.get(key):
                    rec[key] = orphan[key]

    ads: list[dict] = []
    consumed: set[int] = set()
    for rec in records:
        if "id" not in rec or not rec.get("page_name"):
            continue
        consumed.add(id(rec))
        ads.append(
            _with_free_fields(
                {
                    "id": rec["id"],
                    "page_name": rec["page_name"],
                    "status": rec["status"],
                    "first_seen": rec.get("first_seen", ""),
                    "last_seen": rec.get("last_seen", ""),
                    "creative_text": rec.get("creative_text", ""),
                    "library_url": f"{_LIBRARY_BASE}?id={rec['id']}",
                    "page_url": rec.get("page_url", ""),
                    "page_id": rec.get("page_id", ""),
                    "link_url": rec.get("link_url", ""),
                    "link_title": rec.get("link_title", ""),
                    "cta_text": rec.get("cta_text", ""),
                    "link_caption": rec.get("link_caption", ""),
                    "images": rec.get("images", []),
                    "has_video": rec.get("has_video", False),
                    "same_creative_count": rec.get("same_creative_count", 0),
                    "multiple_versions": rec.get("multiple_versions", False),
                }
            )
        )
    # A block carrying the ad marker that yielded no ad (and was not merged
    # into one across a separator boundary) is a card the parse lost. A
    # ``Library ID`` alone is NOT such evidence: at a window edge a capture
    # can start mid-card with the status block whose header never rendered, so
    # counting it would mark an unclipped render partial. Only a block that
    # claims the *body* of a card (``**Sponsored**``, including the payer
    # variant) can prove a card was dropped.
    unparsed = 0
    for block, rec in parsed_blocks:
        markers = _sponsor_marker_count(block)
        if not markers:
            continue
        if rec is None or (id(rec) not in consumed and id(rec) not in consumed_orphans):
            unparsed += 1
            continue
        # Two cards concatenated without the ``* * *`` separator parse as a
        # single ad (the first status block wins), so the others vanish. That
        # reads downstream as those ads having ended — count them as lost.
        if markers > 1:
            unparsed += markers - 1
    meta = {"cards_seen": cards_seen, "unparsed_cards": unparsed}

    if not ads and cards_seen:
        raise ParseError(
            f"{cards_seen} card markers but no parseable ad",
            cards_seen=cards_seen,
            reason=DEAD_RENDER_MARKUP,
        )
    if not ads and not _EMPTY_STATE_RE.search(md):
        # No markers and no empty-state wording (at ANY size): the host
        # snapshotted the page before the results grid hydrated. Report it
        # as a transport/render failure, never as a confident empty listing.
        reason = classify_dead_render(md) or DEAD_RENDER_MARKUP
        raise ParseError(
            f"render ({len(md)} chars) with no card markers or empty-state text",
            cards_seen=0,
            reason=reason,
        )
    return ads, meta


def parse_library_markdown(md: str) -> list[dict]:
    """Parse a rendered Meta Ad Library results page into ad dicts.

    Returns ``[]`` only when the render carries no card markers at all (a
    genuinely empty results page). Markers without any parseable card mean
    the markup changed, so :class:`ParseError` is raised instead.

    Callers that must know whether the capture dropped *some* cards use
    :func:`parse_library_markdown_with_meta`.
    """
    return parse_library_markdown_with_meta(md)[0]


def _content_from_payload(payload: dict) -> str:
    """Extract rendered markdown from a host ``web_extract`` result object.

    Raises :class:`FetchError` for tool-level errors, per-result errors and
    empty content so callers never mistake a failed fetch for "no ads".
    """
    if not isinstance(payload, dict):
        raise FetchError("malformed json")
    error = payload.get("error")
    if error:
        raise FetchError(str(error))

    results = payload.get("results")
    if isinstance(results, list) and results:
        first = results[0] if isinstance(results[0], dict) else {}
        result_error = first.get("error")
        if result_error:
            raise FetchError(str(result_error))
        content = first.get("content") or first.get("markdown")
    elif results == []:
        raise FetchError("empty results")
    else:
        # Tolerate a bare dict carrying the content directly.
        content = payload.get("content") or payload.get("markdown")

    if not content or not isinstance(content, str) or not content.strip():
        raise FetchError("empty content")
    return content


_AD_TEXT_KEYS = (
    "page_name",
    "status",
    "first_seen",
    "last_seen",
    "creative_text",
    "page_url",
    "page_id",
    "link_url",
    "link_title",
    "cta_text",
    "link_caption",
)

# The fields that belong to the creative side of a card, so an orphan header
# can hand them to a status-only half at a capture boundary.
_CREATIVE_KEYS = (
    "creative_text",
    "images",
    "link_url",
    "link_title",
    "cta_text",
    "link_caption",
    "has_video",
    "same_creative_count",
    "multiple_versions",
)

_TRUTHY_STRINGS = frozenset({"1", "true", "yes", "y", "on"})


def _http_url(value) -> str:
    """``value`` when it is an ``http(s)://`` URL, else ``""``.

    Stored JSON payloads are untrusted: a ``javascript:`` or ``data:`` URL
    handed to a report becomes an injection vector, so it is dropped rather
    than passed through.
    """
    if not isinstance(value, str):
        return ""
    url = value.strip()
    if not url.lower().startswith(("http://", "https://")):
        return ""
    return url


def _as_bool(value) -> bool:
    """Strict boolean: the string ``"false"`` is False, not truthy."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return False


def _normalise_ad(rec: dict) -> dict | None:
    """Normalize an already-parsed ad object from a JSON-array payload.

    Old snapshots predate the enrichment fields: every one defaults to an
    empty value so a stored ad never fails to load. Payload values are
    untrusted, so URLs are restricted to http(s), page ids to digits, and
    flags to strict booleans.
    """
    rid = rec.get("id")
    if rid in (None, ""):
        return None
    ad: dict = {"id": str(rid)}
    for key in _AD_TEXT_KEYS:
        ad[key] = str(rec.get(key) or "")
    ad["library_url"] = _http_url(rec.get("library_url")) or (
        f"{_LIBRARY_BASE}?id={ad['id']}"
    )

    # A page id is digits only; a URL or mixed token would poison joins.
    page_id = str(rec.get("page_id") or "").strip()
    ad["page_id"] = page_id if page_id.isdigit() else ""
    ad["link_url"] = _http_url(rec.get("link_url"))

    images = rec.get("images") or []
    if not isinstance(images, list):
        images = [images]
    ad["images"] = [url for url in (_http_url(item) for item in images) if url]
    ad["has_video"] = _as_bool(rec.get("has_video", False))
    try:
        count = int(rec.get("same_creative_count") or 0)
    except (TypeError, ValueError):
        count = 0
    ad["same_creative_count"] = max(count, 0)
    ad["multiple_versions"] = _as_bool(rec.get("multiple_versions", False))
    return _with_payload_free_fields(ad, rec)


def _normalise_card(card) -> dict | None:
    """One card from an untrusted JSON payload, or ``None`` when unusable.

    URLs are restricted to ``http(s)`` (a ``javascript:`` image/link would be
    an injection vector in a report); no video URL is surfaced, because the
    public render does not carry one and ``video`` is always ``None``.
    """
    if not isinstance(card, dict):
        return None
    return {
        "body": str(card.get("body") or ""),
        "cta": str(card.get("cta") or ""),
        "image": _http_url(card.get("image")) or None,
        "link_url": _http_url(card.get("link_url")),
        "title": str(card.get("title") or ""),
        "video": None,
    }


def _with_payload_free_fields(ad: dict, rec: dict) -> dict:
    """P2 fields from a payload, deriving whatever the payload omits.

    A stored payload may already carry ``cta_type``/``display_format``/``cards``
    (this plugin's own JSON export does). Those win when valid; anything else is
    derived from the same render fields the markdown parser uses, so an old
    payload still gets a consistent shape.
    """
    known_cta = str(rec.get("cta_type") or "").strip().upper()
    ad["cta_type"] = known_cta or cta_type(ad.get("cta_text"))
    display = str(rec.get("display_format") or "").strip().lower()
    if display in _PAYLOAD_DISPLAY_FORMATS:
        ad["display_format"] = display
    elif display:
        # An explicit but unverifiable claim (``carousel``, ``multi_images``,
        # anything unknown) is dropped: the public render cannot tell carousel
        # from dco, so echoing the payload would invent a fact.
        ad["display_format"] = ""
    else:
        ad["display_format"] = _display_format(
            ad.get("images") or [], ad["has_video"]
        )
    raw_cards = rec.get("cards")
    cards = []
    if isinstance(raw_cards, list):
        cards = [c for c in (_normalise_card(item) for item in raw_cards) if c]
    ad["cards"] = cards or _cards(ad)
    return ad


def _ads_from_payload_list(
    items: list, limit: int | None
) -> tuple[list[dict], int]:
    """Ads from a JSON-array payload, or :class:`ParseError` if unrecognized.

    Accepts either a list of ``web_extract`` result objects (the envelope as
    an array instead of a dict) or a list of already-parsed ad objects.

    Returns ``(ads_sliced_to_limit, total_parsed)`` so the caller can tell
    whether ``limit`` itself truncated the listing. ``limit=None`` returns
    every ad and reports ``total_parsed`` unchanged.
    """
    if not isinstance(items, list):
        raise FetchError("malformed json")
    if not items:
        raise FetchError("empty results")
    first = items[0]
    if isinstance(first, dict) and any(
        key in first for key in ("content", "markdown", "error")
    ):
        content = _content_from_payload({"results": items})
        parsed = parse_library_markdown(content)
        return parsed if limit is None else parsed[:limit], len(parsed)
    ads = [ad for ad in (_normalise_ad(i) for i in items if isinstance(i, dict)) if ad]
    if not ads:
        raise ParseError(
            "unrecognised JSON array payload", cards_seen=len(items)
        )
    return ads if limit is None else ads[:limit], len(ads)


def _looks_like_json_scalar(text: str) -> bool:
    """True when the whole body is a bare JSON scalar (``null``, ``12345``…).

    A rendered ad-library page is never a single JSON scalar, so decoding one
    means the payload is corrupt; treating it as markdown would produce a
    zero-ad "success" that hides the transport failure.
    """
    head = text[:1]
    if not (
        head in ('"', "-", "+")
        or head.isdigit()
        or text.startswith(("null", "true", "false"))
    ):
        return False
    try:
        decoded = json.loads(text)
    except ValueError:
        return False
    return not isinstance(decoded, (dict, list))


def fetch_ads_with_meta(
    query: str,
    limit: int | None = 20,
    dispatch=None,
    char_limit: int | None = None,
    country: str = "US",
    active_status: str = "all",
    media_type: str = "all",
) -> tuple[list[dict], dict]:
    """Fetch and parse ``query``, returning ``(ads, meta)``.

    ``meta`` is
    ``{"complete": bool, "complete_scope": "rendered_window", "fetched": int,
    "total_returned": int, "fetched_chars": int, "char_limit": int,
    "cards_seen": int, "unparsed_cards": int}``.

    **``complete`` means the rendered window was not clipped — never that the
    whole result set was retrieved.** There is no pagination here: one fetch is
    one public render, and the render itself is a top-N window of Meta's
    results. ``complete_scope`` (always :data:`COMPLETENESS_SCOPE`) is the
    machine-readable reminder. Consequences downstream:

    * an id absent from a *complete* render is absent from the visible window,
      not proven stopped;
    * an ad appearing for the first time may merely have entered the window,
      not launched.

    So ``complete`` rules out "the page was truncated", nothing more. It is a
    *heuristic*, not a guarantee, and it fails toward ``False``. Three
    independent signals make a listing partial:

    * the render reaches the char budget (the host clips oversized pages);
    * the text carries the host's head+tail truncation footer
      (:data:`_TRUNCATION_MARKERS`), which drops cards from the middle;
    * ``limit`` itself sliced the parsed ads (total parsed ``>= limit``), so
      the tail beyond the limit was never returned;
    * a card marker produced no parseable ad (``unparsed_cards > 0``), so the
      capture dropped a card even though the text was not visibly clipped.

    ``cards_seen`` and ``unparsed_cards`` are the parse accounting behind that
    last signal (see :func:`parse_library_markdown_with_meta`).

    ``limit=None`` disables result slicing: every parsed ad is returned and
    the limit signal is inapplicable (it is omitted from the completeness
    test). The char-budget and truncation-footer signals still apply, so
    ``complete`` keeps its meaning: the render itself was not clipped. Use
    this when the caller must see the whole page before narrowing it — for
    example resolving an advertiser name that may appear anywhere in the
    listing.

    A partial listing only suppresses the ``ended`` bucket, so a false
    positive costs a missed retirement report while a false negative
    manufactures ``new`` ads out of a shrunken baseline. Even on a complete
    listing, ``ended``/``new`` remain window-scoped (see above): the diff code
    (:func:`diffing.diff_snapshots`) words them that way.

    ``fetched`` is the number of ads actually returned and ``total_returned``
    the number of ads the render held before ``limit`` sliced it, so a caller
    can see how much of the window it is missing. Both count the parsed ads,
    not the char budget.

    JSON payloads carry whole ads and have no footer, but their length is
    still capped by ``limit``; with ``limit=None`` they are returned whole.

    ``char_limit`` exists so tests (and future tiering) can use a small budget;
    production callers leave it at :data:`_CHAR_LIMIT`.

    ``country`` is the two-letter ad-library market code (default ``US``).
    ``active_status`` and ``media_type`` narrow the listing with the library's
    own free URL parameters (defaults ``all``); invalid values raise
    ``ValueError`` before any network call.
    """
    budget = _CHAR_LIMIT if char_limit is None else max(int(char_limit), 0)
    lim = None if limit is None else max(int(limit), 0)
    if dispatch is None or not callable(dispatch):
        raise FetchError("web_extract unavailable")

    # A pre-hydration shell raises ParseError, and the host caches extractions
    # by URL — retrying the identical URL replays the failure. So a parse
    # failure gets up to _MAX_ATTEMPTS attempts: the first on the plain URL and
    # the rest each with a fresh cache-busting parameter (Meta ignores unknown
    # params). A genuine empty listing returns [] rather than raising, so it
    # never retries.
    #
    # Budget rationale (evals/d3-shell-rootcause.md): p(success) on a *fresh*
    # attempt is 0.34, and with 4 attempts a contested phase still failed ~29%
    # of the time — partly because attempt 1 was usually a 0.01 s host-cache
    # replay of the shell cached during the search phase. Six fresh attempts
    # take that to ~8% (the doc's 6-attempt + wall-clock-cap recommendation)
    # for at most ~50 s of render wait on a genuinely dead phase. The
    # cache-bust on attempt 1 for a URL that already shelled this process
    # reclaims the wasted replay at zero extra fetch cost.
    import uuid

    _wire_url = build_url(
        query,
        country=country,
        active_status=active_status,
        media_type=media_type,
    )
    known_dead = _wire_url in _dead_render_urls
    deadline = time.monotonic() + _FETCH_DEADLINE_S
    last_error: ParseError | FetchError | None = None
    transport_errors = 0
    for attempt in range(_MAX_ATTEMPTS):
        if attempt and time.monotonic() > deadline:
            break
        url = _wire_url
        if attempt or known_dead:
            url = f"{_wire_url}&cache_bust={uuid.uuid4().hex}"
        try:
            return _fetch_once(url, budget, lim, dispatch)
        except ParseError as exc:
            last_error = exc
            if exc.reason == DEAD_RENDER_SHELL:
                # Sticky: the host has this URL's shell cached, so every later
                # fetch for it must start cache-busted even after a success.
                _dead_render_urls.add(_wire_url)
            continue
        except FetchError as exc:
            # Transport failures are transient and unrelated to the URL's
            # cache key: retry once, then surface.
            transport_errors += 1
            last_error = exc
            if transport_errors > _TRANSPORT_RETRIES:
                raise
            continue
    assert last_error is not None
    raise last_error


def _fetch_once(url, budget, lim, dispatch):
    """One fetch+parse round; returns ``(ads, meta)`` or raises."""
    result = dispatch(
        "web_extract",
        {
            "urls": [url],
            "char_limit": budget,
        },
    )
    if isinstance(result, dict):
        content = _content_from_payload(result)
    elif isinstance(result, str):
        if not result.strip():
            raise FetchError("empty content")
        content = result
        stripped = result.lstrip()
        decoded = None
        if stripped.startswith(("{", "[")):
            try:
                decoded = json.loads(result)
            except ValueError:
                if stripped.startswith("{"):
                    # A `{`-shaped body that will not decode is a transport
                    # failure, not an empty render. Parsing it as markdown
                    # would silently turn corruption into a zero-ad success.
                    raise FetchError("malformed json") from None
                # A render can legitimately begin with a markdown link `[`.
        if isinstance(decoded, dict):
            content = _content_from_payload(decoded)
        elif isinstance(decoded, list):
            ads, total = _ads_from_payload_list(decoded, lim)
            # With limit=None nothing was sliced off, so the listing
            # is whole: a JSON array carries no footer or char budget.
            # `total == lim` means every parsed ad was returned; only
            # a total beyond the limit proves the tail was sliced.
            return ads, {
                "complete": True if lim is None else total <= lim,
                "complete_scope": COMPLETENESS_SCOPE,
                "fetched": len(ads),
                "total_returned": total,
                "fetched_chars": 0,
                "char_limit": budget,
                # JSON carries whole ads, not rendered cards; an item that
                # failed normalisation (no id) is still reported as dropped.
                "cards_seen": total,
                "unparsed_cards": max(len(decoded) - total, 0),
            }
        elif decoded is not None:
            # Any other decoded top-level value (scalar/null/bool) is a
            # corrupt payload, never a rendered page.
            raise FetchError("malformed json")
        elif _looks_like_json_scalar(result):
            raise FetchError("malformed json")
    else:
        raise FetchError("web_extract returned no result")

    parsed, parse_meta = parse_library_markdown_with_meta(content)
    # A marker that produced no ad is a card the parse lost, so the render is
    # not complete even when it was neither clipped nor sliced: dropping a
    # card would otherwise read downstream as that ad having ended.
    unparsed_cards = parse_meta["unparsed_cards"]
    complete = (
        len(content) < budget
        and (lim is None or len(parsed) < lim)
        and not any(marker in content for marker in _TRUNCATION_MARKERS)
        and unparsed_cards == 0
    )
    meta = {
        "complete": complete,
        "complete_scope": COMPLETENESS_SCOPE,
        "fetched": len(parsed) if lim is None else min(len(parsed), lim),
        "total_returned": len(parsed),
        "fetched_chars": len(content),
        "char_limit": budget,
        "cards_seen": parse_meta["cards_seen"],
        "unparsed_cards": unparsed_cards,
    }
    return parsed if lim is None else parsed[:lim], meta


def fetch_ads(
    query: str,
    limit: int | None = 20,
    dispatch=None,
    country: str = "US",
    active_status: str = "all",
    media_type: str = "all",
) -> list[dict]:
    """Fetch and parse the ad library for ``query`` via host ``web_extract``.

    Returns ``[]`` only when a fetch succeeded and the render carried no card
    markers at all; transport/decoding failures raise :class:`FetchError` and
    an unparseable render raises :class:`ParseError`.

    ``limit=None`` returns every parsed ad (see
    :func:`fetch_ads_with_meta`).

    Ads only, for backwards compatibility. Callers that must distinguish a
    complete listing from a truncated one use :func:`fetch_ads_with_meta`.
    """
    return fetch_ads_with_meta(
        query,
        limit=limit,
        dispatch=dispatch,
        country=country,
        active_status=active_status,
        media_type=media_type,
    )[0]