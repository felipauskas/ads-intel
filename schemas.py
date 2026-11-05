AD_SEARCH = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Brand, advertiser, or keyword to search public ad libraries for"},
        "limit": {"type": "integer", "description": "Max ads to return (default 20)"},
    },
    "required": ["query"],
}
AD_WATCH = {"type": "object", "properties": {"action": {"type": "string", "enum": ["add", "remove", "list"], "description": "Watchlist action"}, "query": {"type": "string", "description": "Search query to add/remove"}}, "required": ["action"]}
AD_CHECK = {"type": "object", "properties": {}, "description": "Fetch every watchlist entry, diff against the last snapshot, report and store changes"}
