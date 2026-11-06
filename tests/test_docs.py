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

    # Rule 5: the repo is not published yet, so no install-from-GitHub line.
    assert "felipauskas/ads-intel" not in text, (
        "README must not point at a GitHub slug: the repo is not published"
    )
    assert "local" in lowered, "README must describe the local install path"
