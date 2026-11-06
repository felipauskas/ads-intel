AD_SEARCH = {
    "type": "object",
    "description": (
        "Use when you want to see who is running ads for a brand, advertiser or "
        "keyword right now or recently. Searches the public Meta Ad Library and "
        "returns ad id, page name, run status, start/end dates, creative text "
        "and a library URL. It is a keyword search, so results include any page "
        "that mentions the term. Supports an optional result limit (default 20)."
    ),
    "properties": {
        "query": {"type": "string", "description": "Brand, advertiser, or keyword to search public ad libraries for"},
        "limit": {"type": "integer", "description": "Max ads to return (default 20)"},
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
        "changed ads."
    ),
    "properties": {"action": {"type": "string", "enum": ["add", "remove", "list"], "description": "Watchlist action"}, "query": {"type": "string", "description": "Search query to add/remove"}},
    "required": ["action"],
}
AD_CHECK = {
    "type": "object",
    "description": (
        "Use when you want to know what changed since the last check for every "
        "watchlisted query. Fetches each entry, diffs it against the stored "
        "snapshot and reports new, ended and changed ads. The first check after "
        "adding a watch seeds the baseline and reports every ad as new; a "
        "failed or empty fetch is skipped rather than reported as all-ended. "
        "Each result carries `partial`: true when the fetch was clipped by the "
        "char budget, the host's truncation footer, or the 20-ad result limit "
        "(unknown completeness counts as partial). A partial result suppresses "
        "the `ended` bucket and merges the fetched ads into the saved baseline; "
        "new and changed ads stay accurate. Watches with 20 or more live ads "
        "therefore never report ended ads."
    ),
    "properties": {},
}
