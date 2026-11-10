"""README disclosure contract.

The plugin touches the network, the local filesystem and a third-party site
whose terms do not authorise automated collection. Those facts must be stated
in the README, in a form a catalog reviewer can check mechanically.
"""

from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def _readme() -> str:
    assert README.exists(), "README.md is missing"
    return README.read_text(encoding="utf-8")


def _lower() -> str:
    return _readme().lower()


def test_readme_discloses_network_filesystem_and_credentials():
    text = _readme()
    lowered = _lower()

    # Network: the one host the plugin causes Hermes to fetch.
    assert "facebook.com" in text, "README must name the network host"
    assert "web_extract" in text, "README must say which Hermes surface fetches"

    # Filesystem: every artifact the plugin writes.
    for token in ("watchlist.json", "snapshots", "reports/"):
        assert token in text, f"README must disclose plugin-data path {token!r}"

    # Credentials: none are read, needed or stored.
    assert "no credentials" in lowered, "README must state 'no credentials'"

    # Terms of service posture.
    assert "terms" in lowered, "README must state the ToS posture"

    # Limitations a catalog reviewer would otherwise discover the hard way.
    assert "partial" in lowered, "README must explain partial results"
    assert "120" in text and "truncat" in lowered, "README must state the truncation limit"
    assert "parse_failed" in text, "README must document the parse_failed reason"
    assert "country" in lowered, "README must document the country parameter"
    assert "0.85" in text, "README must state the advertiser-resolution score ceiling"

    # Rule 5 satisfied: the repo is public and the README points at it, while
    # still saying the catalog entry has not landed (so install is by repo id).
    assert "https://github.com/felipauskas/ads-intel" in text, (
        "README must link the published repo"
    )
    assert "not yet in the Hermes catalog" in text, (
        "README must state the catalog status plainly"
    )

    # The shipped tree now scans clean and installs without an override; --force
    # remains documented only for an older tree that still tracks the evidence.
    assert "hermes plugins install felipauskas/ads-intel\n" in text, (
        "README install command must work non-interactively on the shipped tree"
    )
    assert "hermes plugins install felipauskas/ads-intel --force" not in text, (
        "README must not require --force for the clean shipped tree"
    )
    assert "--force" in text, "README must still document --force for tracked evidence"
    assert "Blocked" in text, "README must say a caution verdict blocks non-interactive installs"
    assert "clean security scan" in lowered, "README must state the shipped scan is clean"
    assert "untracked" in lowered and "regenerable" in lowered, (
        "README must say the eval evidence is untracked and regenerable"
    )
    assert "warning-free" in lowered, "README must not imply a warning-free install"

    _assert_readme_numbers_match_the_code()


def _assert_readme_numbers_match_the_code():
    """Every number the README promises is pinned to the module that owns it.

    The token checks only prove the README *mentions* a limit; these asserts
    prove the mention still describes the code, so the docs cannot drift from
    the constants and key scheme a reader relies on.
    """
    import resolve
    import sources
    import store

    # Truncation budget quoted in "Limitations" (`char_limit=120000`).
    assert sources._CHAR_LIMIT == 120_000

    # `0.85` normalized ceiling quoted in "Advertiser resolution".
    assert resolve.score_candidate("KFC", "K.F.C.") == 0.85
    # ...and the `0.80` exact score that is also the match threshold.
    assert resolve.score_candidate("KFC", "KFC") == 0.80

    # `reports/<sha1>.html` — the directory the Disclosures name.
    html = store.report_paths("KFC", "US")["html"]
    assert html.parent.name == "reports"
    assert html.suffix == ".html"

    # Artifact filenames hash `(query, country, advertiser)`: a market change
    # or an advertiser filter must never share another watch's file.
    us = store.report_paths("KFC", "US")["html"].name
    ae = store.report_paths("KFC", "AE")["html"].name
    filtered = store.report_paths("KFC", "US", "KFC")["html"].name
    assert len({us, ae, filtered}) == 3, "report key ignores country or advertiser"
