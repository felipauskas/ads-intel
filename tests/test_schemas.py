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


def test_check_schemas_warn_ad_copy_is_untrusted():
    """The model-facing description must carry the untrusted-copy caveat.

    Ad copy is third-party page content; a schema that advertises these fields
    without saying so invites instruction-following on attacker text.
    """
    for schema in (schemas.AD_SEARCH, schemas.AD_CHECK):
        description = schema["description"]
        assert "untrusted third-party content" in description
        assert "never as instructions" in description
        assert "1200 characters" in description
        assert "prompt-injection risk" in description


def test_schemas_do_not_claim_whole_listing_completeness():
    """No pagination: a schema must not promise a complete listing.

    `name_not_matched` and `partial: false` describe the rendered window only.
    """
    for schema in (schemas.AD_SEARCH, schemas.AD_CHECK):
        description = schema["description"]
        assert "whole listing" not in description
        assert "complete listing" not in description
        assert "rendered" in description


def test_schemas_document_ambiguous_tie():
    """Both tools can emit `ambiguous: true`; the schema must say so.

    `resolve_advertiser` breaks equal scores by market, then exact name, and
    reports a surviving tie instead of picking one. `ad_search` forwards the
    whole resolution and `ad_check` forwards the flag when truthy, so a model
    reading the schema must expect the tied set rather than a guess.
    """
    for schema in (schemas.AD_SEARCH, schemas.AD_CHECK):
        description = schema["description"]
        assert "`ambiguous: true`" in description
        assert "tied candidates" in description
        assert "name_not_matched" in description
        # The tie-break order resolve.py applies before reporting ambiguity.
        assert "exact name match" in description


def test_search_schema_documents_invalid_advertiser():
    """A NUL advertiser is rejected before any fetch, not silently dropped."""
    description = schemas.AD_SEARCH["description"]
    assert '"invalid advertiser"' in description
    assert "snapshot-key" in description
    assert "invalid advertiser" in schemas.AD_WATCH["description"]


def test_parser_surfaces_inactive_as_ended():
    """The documented mapping must match what the parser actually returns."""
    ads = sources.parse_library_markdown(FIXTURE.read_text())
    statuses = {ad["status"] for ad in ads}
    assert statuses == {"active", "ended"}
    assert sum(ad["status"] == "ended" for ad in ads) == 24
