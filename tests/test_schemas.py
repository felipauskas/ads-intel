"""Contract tests for the tool schemas.

The README already states that the library's filter vocabulary and the
surfaced per-ad ``status`` vocabulary differ. The schema is the surface a
model reads before calling the tool, so it must say the same thing.
"""

from pathlib import Path

import schemas
import sources

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "library_page.md"


def test_search_schema_documents_inactive_to_ended_mapping():
    description = schemas.AD_SEARCH["description"]
    assert 'filter name is not the surfaced value' in description
    assert '"Inactive" is surfaced as status "ended"' in description
    # The round-trip fact a caller needs: filtering `inactive` yields `ended`.
    assert "`inactive` filter returns ads whose `status` is `ended`" in description


def test_check_schema_documents_surfaced_status_vocabulary():
    description = schemas.AD_CHECK["description"]
    assert '"Inactive" is surfaced as "ended"' in description


def test_parser_surfaces_inactive_as_ended():
    """The documented mapping must match what the parser actually returns."""
    ads = sources.parse_library_markdown(FIXTURE.read_text())
    statuses = {ad["status"] for ad in ads}
    assert statuses == {"active", "ended"}
    assert sum(ad["status"] == "ended" for ad in ads) == 24
