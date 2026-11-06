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
_PAGE_LINK_RE = re.compile(
    r"^\[([^\]]+)\]\(https://www\.facebook\.com/[^)]*\)"
    r"(?:\s+with\s+\[[^\]]+\]\([^)]*\))?$"
)
_IMAGE_ALT_RE = re.compile(r"^!\[([^\]]*)\]\(")
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


def build_url(query: str, country: str = "US") -> str:
    """Public ad-library search URL for ``query``."""
    return (
        f"{_LIBRARY_BASE}?active_status=all&ad_type=all&country={country}"
        f"&q={_quote_plus(query)}&media_type=all&search_type=keyword_unordered"
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


def _page_name_before(lines: list[str], sponsored_idx: int) -> str:
    for raw in reversed(lines[:sponsored_idx]):
        line = raw.strip()
        if not line:
            continue
        link = _PAGE_LINK_RE.match(line)
        if link:
            return link.group(1).strip()
        image = _IMAGE_ALT_RE.match(line)
        if image and image.group(1).strip():
            return image.group(1).strip()
        # Other markdown between the label and "Sponsored" means there is no
        # page label for this card.
        if line != "**Sponsored**":
            return ""
    return ""


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
        ad["page_name"] = _page_name_before(lines, sponsored_idx)
        end = status_idx if status_idx is not None else len(lines)
        ad["creative_text"] = _clean_creative(lines[sponsored_idx + 1 : end])

    return ad or None


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
            rec["page_name"] = orphans.pop(0)["page_name"]

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


_AD_TEXT_KEYS = ("page_name", "status", "first_seen", "last_seen", "creative_text")


def _normalise_ad(rec: dict) -> dict | None:
    """Normalize an already-parsed ad object from a JSON-array payload."""
    rid = rec.get("id")
    if rid in (None, ""):
        return None
    ad: dict = {"id": str(rid)}
    for key in _AD_TEXT_KEYS:
        ad[key] = str(rec.get(key) or "")
    ad["library_url"] = rec.get("library_url") or f"{_LIBRARY_BASE}?id={ad['id']}"
    return ad


def _ads_from_payload_list(items: list, limit: int) -> tuple[list[dict], int]:
    """Ads from a JSON-array payload, or :class:`ParseError` if unrecognized.

    Accepts either a list of ``web_extract`` result objects (the envelope as
    an array instead of a dict) or a list of already-parsed ad objects.

    Returns ``(ads_sliced_to_limit, total_parsed)`` so the caller can tell
    whether ``limit`` itself truncated the listing.
    """
    if not items:
        raise FetchError("empty results")
    first = items[0]
    if isinstance(first, dict) and any(
        key in first for key in ("content", "markdown", "error")
    ):
        content = _content_from_payload({"results": items})
        parsed = parse_library_markdown(content)
        return parsed[:limit], len(parsed)
    ads = [ad for ad in (_normalise_ad(i) for i in items if isinstance(i, dict)) if ad]
    if not ads:
        raise ParseError(
            "unrecognised JSON array payload", cards_seen=len(items)
        )
    return ads[:limit], len(ads)


def fetch_ads_with_meta(
    query: str,
    limit: int = 20,
    dispatch=None,
    char_limit: int | None = None,
) -> tuple[list[dict], dict]:
    """Fetch and parse ``query``, returning ``(ads, meta)``.

    ``meta`` is
    ``{"complete": bool, "fetched_chars": int, "char_limit": int}``.

    Completeness is a *heuristic*, not a guarantee, and it fails toward
    ``False``. Three independent signals make a listing partial:

    * the render reaches the char budget (the host clips oversized pages);
    * the text carries the host's head+tail truncation footer
      (:data:`_TRUNCATION_MARKERS`), which drops cards from the middle;
    * ``limit`` itself sliced the parsed ads (total parsed ``>= limit``), so
      the tail beyond the limit was never returned.

    A partial listing only suppresses the ``ended`` bucket, so a false
    positive costs a missed retirement report while a false negative
    manufactures ``new`` ads out of a shrunken baseline.

    JSON payloads carry whole ads and have no footer, but their length is
    still capped by ``limit``.

    ``char_limit`` exists so tests (and future tiering) can use a small budget;
    production callers leave it at :data:`_CHAR_LIMIT`.
    """
    budget = _CHAR_LIMIT if char_limit is None else max(int(char_limit), 0)
    lim = max(int(limit), 0)
    if dispatch is None or not callable(dispatch):
        raise FetchError("web_extract unavailable")
    result = dispatch(
        "web_extract",
        {"urls": [build_url(query)], "char_limit": budget},
    )
    if isinstance(result, dict):
        content = _content_from_payload(result)
    elif isinstance(result, str):
        if not result.strip():
            raise FetchError("empty content")
        content = result
        stripped = result.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                decoded = json.loads(result)
            except ValueError:
                pass  # not JSON (markdown can start with '['): raw content
            else:
                if isinstance(decoded, dict):
                    content = _content_from_payload(decoded)
                elif isinstance(decoded, list):
                    ads, total = _ads_from_payload_list(decoded, lim)
                    return ads, {
                        "complete": total < lim,
                        "fetched_chars": 0,
                        "char_limit": budget,
                    }
    else:
        raise FetchError("web_extract returned no result")

    parsed = parse_library_markdown(content)
    complete = (
        len(content) < budget
        and len(parsed) < lim
        and not any(marker in content for marker in _TRUNCATION_MARKERS)
    )
    meta = {
        "complete": complete,
        "fetched_chars": len(content),
        "char_limit": budget,
    }
    return parsed[:lim], meta


def fetch_ads(query: str, limit: int = 20, dispatch=None) -> list[dict]:
    """Fetch and parse the ad library for ``query`` via host ``web_extract``.

    Returns ``[]`` only when a fetch succeeded and the render carried no card
    markers at all; transport/decoding failures raise :class:`FetchError` and
    an unparseable render raises :class:`ParseError`.

    Ads only, for backwards compatibility. Callers that must distinguish a
    complete listing from a truncated one use :func:`fetch_ads_with_meta`.
    """
    return fetch_ads_with_meta(query, limit=limit, dispatch=dispatch)[0]
