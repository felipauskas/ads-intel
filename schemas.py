AD_SEARCH = {
    "type": "object",
    "description": (
        "Use when you want to see who is running ads for a brand, advertiser or "
        "keyword right now or recently. Searches the public Meta Ad Library and "
        "returns ad id, page name, run status, start/end dates, creative text "
        "and a library URL. It is a keyword search, so results include any page "
        "that mentions the term. Supports an optional result limit (default 20) "
        "and an optional two-letter market code (`country`, default US). Pass "
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
        "snapshot alone."
    ),
    "properties": {"action": {"type": "string", "enum": ["add", "remove", "list"], "description": "Watchlist action"}, "query": {"type": "string", "description": "Search query to add/remove"}, "advertiser": {"type": "string", "description": "Optional page/brand name to resolve and watch (used on add)"}, "country": {"type": "string", "description": "Two-letter market code to watch (default US); used on add", "pattern": "^[A-Z]{2}$", "default": "US"}},
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
        "is still reported. Each result also carries "
        "`artifacts: {html, digest}`: paths to a single-file, offline HTML "
        "report (all ads as cards) and its JSON digest of the same counts; "
        "a report write failure sets `artifacts` to `{error}` without "
        "failing the check."
    ),
    "properties": {},
}
