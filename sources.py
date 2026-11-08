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


# An empty results page renders short (a few hundred chars of chrome). A render
# past this size with no card markers at all means the page shape drifted, not
# that the advertiser has no ads.
_MAX_EMPTY_RENDER_CHARS = 5000


class FetchError(RuntimeError):
    """The host fetch failed or returned no usable content."""


class ParseError(Exception):
    """The page rendered content that looks like ads but parsed to none.

    Raised instead of returning ``[]`` so a markup change is never mistaken
    for "this advertiser has no ads".

    ``cards_seen`` is the number of card markers found in the render.
    """

    def __init__(self, message: str = "no cards parsed", cards_seen: int = 0):
        super().__init__(message)
        self.cards_seen = cards_seen


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
_PAGE_LINK_URL_RE = re.compile(
    r"^\[([^\]]+)\]\((https://www\.facebook\.com/[^)\s]*)\)"
)
_NUMERIC_PAGE_RE = re.compile(r"facebook\.com/(\d+)(?:[/?#]|$)")
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


def _has_card_marker(lines: list[str]) -> bool:
    """A block that claims to be an ad card, whether or not it parses.

    Card markers, not separators, are the signal: a genuinely empty results
    page still has ``* * *`` chrome separators but no ``**Sponsored**`` or
    ``Library ID`` anywhere.
    """
    for raw in lines:
        line = raw.strip()
        if line == "**Sponsored**" or line.startswith("Library ID:"):
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


def _clean_creative(lines: list[str]) -> str:
    kept: list[str] = []
    skipping_link_block = False
    for raw in lines:
        line = raw.strip()
        if skipping_link_block:
            # A multi-line markdown link/CTA continues until the "](" line.
            if "](" in line:
                skipping_link_block = False
            continue
        if line.startswith("["):
            # A link-only line is dropped; an unclosed one starts a CTA block.
            if line.endswith(")") and "](" in line:
                continue
            skipping_link_block = True
            continue
        if line in _NOISE_LINES or line.startswith(_NOISE_PREFIXES):
            continue
        if line.startswith("!["):
            continue
        kept.append(line)
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


def _page_label_before(lines: list[str], sponsored_idx: int) -> tuple[str, str]:
    """``(page_name, page_url)`` for the label above ``**Sponsored**``.

    The URL is the label's own link (``facebook.com/nike/`` or a numeric
    profile id), taken from the first link of a co-advertiser label such as
    ``[Noemimisma](…) with [Nike](…)``. When only an image alt text names the
    page, it is the name and the URL is ``""``.
    """
    for raw in reversed(lines[:sponsored_idx]):
        line = raw.strip()
        if not line:
            continue
        link = _PAGE_LINK_URL_RE.match(line)
        if link:
            return link.group(1).strip(), link.group(2).strip()
        image = _IMAGE_ALT_RE.match(line)
        if image and image.group(1).strip():
            return image.group(1).strip(), ""
        if line != "**Sponsored**":
            return "", ""
    return "", ""


def _numeric_page_id(page_url: str) -> str:
    """The digits in a numeric profile URL, else ``""``.

    Vanity handles (``facebook.com/nike/``) carry no page id in the public
    render, and inventing one would poison joins.
    """
    match = _NUMERIC_PAGE_RE.search(page_url or "")
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
    # The first segment is the display domain (AD.DOUBLECLICK.NET); drop it.
    title_parts = [s for s in segments[:-1] if not _DOMAIN_RE.match(s)]
    return {
        "link_url": dest,
        "link_title": " ".join(title_parts),
        "cta_text": cta_text,
    }


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
        (i for i, line in enumerate(lines) if line.strip() == "**Sponsored**"),
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


def parse_library_markdown(md: str) -> list[dict]:
    """Parse a rendered Meta Ad Library results page into ad dicts.

    Returns ``[]`` only when the render carries no card markers at all (a
    genuinely empty results page). Markers without any parseable card mean
    the markup changed, so :class:`ParseError` is raised instead.
    """
    if not md or not isinstance(md, str):
        return []
    blocks = _card_blocks(md)
    records = [rec for rec in (_parse_block(b) for b in blocks) if rec]
    cards_seen = sum(1 for block in blocks if _has_card_marker(block))

    # Recover cards cut in two by a capture/separator boundary: a status block
    # with no page label picks up a page label with no status block. Complete
    # cards always consume their own label, so only leftovers pair here.
    orphans = [r for r in records if "id" not in r and r.get("page_name")]
    for rec in records:
        if "id" in rec and not rec.get("page_name") and orphans:
            orphan = orphans.pop(0)
            rec["page_name"] = orphan["page_name"]
            rec["page_url"] = orphan.get("page_url", "")
            rec["page_id"] = orphan.get("page_id", "")
            # The creative lives on the header side of the split. Carry it
            # over rather than reporting the status-only half as a blank ad.
            for key in _CREATIVE_KEYS:
                if not rec.get(key) and orphan.get(key):
                    rec[key] = orphan[key]

    ads: list[dict] = []
    for rec in records:
        if "id" not in rec or not rec.get("page_name"):
            continue
        ads.append(
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
                "images": rec.get("images", []),
                "has_video": rec.get("has_video", False),
                "same_creative_count": rec.get("same_creative_count", 0),
                "multiple_versions": rec.get("multiple_versions", False),
            }
        )
    if not ads and cards_seen:
        raise ParseError(
            f"{cards_seen} card markers but no parseable ad", cards_seen=cards_seen
        )
    if not ads and len(md) > _MAX_EMPTY_RENDER_CHARS:
        raise ParseError(
            f"long render ({len(md)} chars) with no card markers", cards_seen=0
        )
    return ads


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
)

# The fields that belong to the creative side of a card, so an orphan header
# can hand them to a status-only half at a capture boundary.
_CREATIVE_KEYS = (
    "creative_text",
    "images",
    "link_url",
    "link_title",
    "cta_text",
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
    ``{"complete": bool, "fetched": int, "total_returned": int,
    "fetched_chars": int, "char_limit": int}``.

    ``fetched`` is the number of ads actually returned and ``total_returned``
    the number of ads the render held before ``limit`` sliced it, so a caller
    can see how much of the listing it is missing. Both count the parsed ads,
    not the char budget.

    Completeness is a *heuristic*, not a guarantee, and it fails toward
    ``False``. Three independent signals make a listing partial:

    * the render reaches the char budget (the host clips oversized pages);
    * the text carries the host's head+tail truncation footer
      (:data:`_TRUNCATION_MARKERS`), which drops cards from the middle;
    * ``limit`` itself sliced the parsed ads (total parsed ``>= limit``), so
      the tail beyond the limit was never returned.

    ``limit=None`` disables result slicing: every parsed ad is returned and
    the limit signal is inapplicable (it is omitted from the completeness
    test). The char-budget and truncation-footer signals still apply, so
    ``complete`` keeps its meaning: the render itself was not clipped. Use
    this when the caller must see the whole page before narrowing it — for
    example resolving an advertiser name that may appear anywhere in the
    listing.

    A partial listing only suppresses the ``ended`` bucket, so a false
    positive costs a missed retirement report while a false negative
    manufactures ``new`` ads out of a shrunken baseline.

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
    result = dispatch(
        "web_extract",
        {
            "urls": [
                build_url(
                    query,
                    country=country,
                    active_status=active_status,
                    media_type=media_type,
                )
            ],
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
                "fetched": len(ads),
                "total_returned": total,
                "fetched_chars": 0,
                "char_limit": budget,
            }
        elif decoded is not None:
            # Any other decoded top-level value (scalar/null/bool) is a
            # corrupt payload, never a rendered page.
            raise FetchError("malformed json")
        elif _looks_like_json_scalar(result):
            raise FetchError("malformed json")
    else:
        raise FetchError("web_extract returned no result")

    parsed = parse_library_markdown(content)
    complete = (
        len(content) < budget
        and (lim is None or len(parsed) < lim)
        and not any(marker in content for marker in _TRUNCATION_MARKERS)
    )
    meta = {
        "complete": complete,
        "fetched": len(parsed) if lim is None else min(len(parsed), lim),
        "total_returned": len(parsed),
        "fetched_chars": len(content),
        "char_limit": budget,
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