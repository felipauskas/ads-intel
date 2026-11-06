AD_SEARCH = {
    "type": "object",
    "description": (
        "Use when you want to see who is running ads for a brand, advertiser or "
        "keyword right now or recently. Searches the public Meta Ad Library and "
        "returns ad id, page name, run status, start/end dates, creative text, "
        "a library URL, page URL/id, destination link (url/title), CTA text, "
        "creative image URLs, a video flag, and creative-grouping signals "
        "(same_creative_count, multiple_versions). Everything comes from the "
        "free public render: no API key, and no spend/impressions or video "
        "file URLs are invented. It is a keyword search, so results include any page "
        "that mentions the term. Supports an optional result limit (default 20) "
        "and an optional two-letter market code (`country`, default US). "
        "Optional `active_status` (all|active|inactive, default all) and "
        "`media_type` (all|image|video, default all) narrow the listing with "
        "the library's own free URL parameters; an unsupported value returns "
        "`{\"error\": \"invalid_active_status\"}` or "
        "`{\"error\": \"invalid_media_type\"}`. Pass "
        "`advertiser` to keep only ads from that brand's page: the keyword hits "
        "are resolved to one page name by score (exact 0.80, normalized 0.85, "
        "substring 0.60, threshold 0.80), against the whole listing before "
        "`limit` is applied, so a page past the first 20 hits still resolves. "
        "A target no page matches returns "
        "`{\"error\": \"name_not_matched\", target, candidates, threshold}` "
        "instead of unfiltered ads."
    ),
    "properties": {
        "query": {"type": "string", "description": "Brand, advertiser, or keyword to search public ad libraries for"},
        "advertiser": {
            "type": "string",
            "description": "Optional page/brand name to resolve and keep only that page's ads",
        },
        "limit": {"type": "integer", "description": "Max ads to return (default 20)"},
        "country": {
            "type": "string",
            "description": "Two-letter ad-library market code, uppercase (e.g. US, GB, AE). Defaults to US.",
            "pattern": "^[A-Z]{2}$",
            "default": "US",
        },
        "active_status": {
            "type": "string",
            "enum": ["all", "active", "inactive"],
            "description": "Ad run-status filter (default all)",
            "default": "all",
        },
        "media_type": {
            "type": "string",
            "enum": ["all", "image", "video"],
            "description": "Creative media-type filter (default all)",
            "default": "all",
        },
    },
    "required": ["query"],
}
AD_WATCH = {
    "type": "object",
    "description": (
        "Use when you want to track a competitor or keyword over time. "
        "'add' saves a search query to the local watchlist (query required), "
        "'remove' deletes a saved query, and 'list' shows the current watchlist. "
        "Run ad_check afterwards to seed the baseline and detect new, ended or "
        "changed ads. Pass `advertiser` on add to track one brand's page: "
        "ad_check then resolves each entry to that page and keeps only its ads; "
        "an unresolvable name reports `name_not_matched` and leaves the "
        "snapshot alone. Pass `active_status` (all|active|inactive) or "
        "`media_type` (all|image|video) on add to watch a narrowed slice: the "
        "filters are stored on the entry and the watch keeps its own snapshot "
        "and report, so it never shares a baseline with an unfiltered one. "
        "Invalid values return `invalid_active_status` / "
        "`invalid_media_type`."
    ),
    "properties": {"action": {"type": "string", "enum": ["add", "remove", "list"], "description": "Watchlist action"}, "query": {"type": "string", "description": "Search query to add/remove"}, "advertiser": {"type": "string", "description": "Optional page/brand name to resolve and watch (used on add)"}, "country": {"type": "string", "description": "Two-letter market code to watch (default US); used on add", "pattern": "^[A-Z]{2}$", "default": "US"}, "active_status": {"type": "string", "enum": ["all", "active", "inactive"], "description": "Ad run-status filter stored on the watch entry (default all); used on add", "default": "all"}, "media_type": {"type": "string", "enum": ["all", "image", "video"], "description": "Creative media-type filter stored on the watch entry (default all); used on add", "default": "all"}},
    "required": ["action"],
}
AD_CHECK = {
    "type": "object",
    "description": (
        "Use when you want to know what changed since the last check for every "
        "watchlisted query. Fetches each entry, diffs it against the stored "
        "snapshot and reports new, ended and changed ads. Each entry is fetched "
        "in its own two-letter market (`country`, default US). The first check "
        "after "
        "adding a watch seeds the baseline and reports every ad as new; a "
        "failed or empty fetch is skipped rather than reported as all-ended. "
        "Each result carries `partial`: true when the fetch was clipped by the "
        "char budget, the host's truncation footer, or — on an unfiltered "
        "watch — the 20-ad result limit (unknown completeness counts as "
        "partial). A watch with an `advertiser` resolves and filters against "
        "the full listing before diffing, so a brand page that appears past "
        "the first 20 keyword hits still resolves and all of that page's ads "
        "are tracked; `name_not_matched` therefore means the page is absent "
        "from the whole listing (on a partial result it only means the page "
        "was not in the part that rendered). A partial result suppresses "
        "the `ended` bucket and merges the fetched ads into the saved baseline; "
        "new and changed ads stay accurate. Endings are suppressed only for ids "
        "missing from the clipped page: a status flip on an ad that did render "
        "is still reported. Bucket summaries carry the enriched fields: page_url, "
        "page_id, link_url, link_title, cta_text, images, has_video, "
        "same_creative_count and multiple_versions (empty/zero/false when the "
        "public render did not show them). Each result also carries "
        "`artifacts: {html, digest}`: paths to a single-file, offline HTML "
        "report (all ads as cards) and its JSON digest of the same counts; "
        "a report write failure sets `artifacts` to `{error}` without "
        "failing the check. Skipped rows (`skipped: true` with `reason`) and "
        "failed rows (`error`) keep the same contract: they carry `partial: "
        "true` and `artifacts: {error}` because no report was written."
    ),
    "properties": {},
}
