"""ads-intel — public ad library search + competitor watch."""
import logging

logger = logging.getLogger(__name__)


def register(ctx):
    # Imported here, not at module level: pytest treats a hyphenated plugin
    # directory as a package root and imports this file as a bare ``__init__``,
    # where a relative import at module level raises ImportError.
    from . import schemas, tools

    tools.set_ctx(ctx)
    ctx.register_tool(name="ad_search", toolset="ads-intel",
                      schema=schemas.AD_SEARCH, handler=tools.ad_search)
    ctx.register_tool(name="ad_watch", toolset="ads-intel",
                      schema=schemas.AD_WATCH, handler=tools.ad_watch)
    ctx.register_tool(name="ad_check", toolset="ads-intel",
                      schema=schemas.AD_CHECK, handler=tools.ad_check)
