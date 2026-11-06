"""Manifest contract: the fields Hermes catalog admission requires.

Parsed with a tiny stdlib reader so the test suite stays dependency-free
(the plugin itself declares ``python_dependencies: []``).

The reader is deliberately strict: it fails on duplicate keys and on raw
values that would silently change meaning under a real YAML parser, so a
typo cannot pass this suite while breaking the manifest Hermes actually
loads.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "plugin.yaml"
INIT = ROOT / "__init__.py"

EXPECTED_TOOLS = {"ad_search", "ad_watch", "ad_check"}
EXPECTED_TAGS = ["ads", "competitor-intelligence", "marketing", "ad-library"]

# Local mirror of hermes_cli.plugins_manifest._KNOWN_MANIFEST_FIELDS, restricted
# to the fields this plugin uses. A key outside this set is a typo or a
# catalog-entry field (e.g. ``maintainer``) that the loader ignores with a
# warning on every load.
KNOWN_FIELDS = {
    "name",
    "label",
    "version",
    "description",
    "author",
    "license",
    "homepage",
    "tags",
    "manifest_version",
    "requires_hermes",
    "python_dependencies",
    "capabilities",
    "provides_tools",
}

NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Leading YAML indicators that turn an intended plain scalar into syntax.
_INDICATORS = ">|&*!{"


def _scalar(raw):
    raw = raw.strip()
    if raw.startswith("["):
        if not raw.endswith("]"):
            pytest.fail(f"unterminated flow sequence: {raw!r}")
        inner = raw[1:-1].strip()
        return [p.strip().strip("\"'") for p in inner.split(",")] if inner else []
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw[0] in _INDICATORS:
        pytest.fail(f"unquoted value starts with YAML indicator {raw[0]!r}: {raw!r}")
    if ": " in raw:
        pytest.fail(f"unquoted value contains ': ' (would parse as a mapping): {raw!r}")
    return raw


def load_manifest(path=MANIFEST):
    data, current = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if not isinstance(current, list):
                pytest.fail(f"list item outside a key: {line!r}")
            assert isinstance(current, list)  # narrowing for type checkers
            current.append(_scalar(stripped[2:]))
            continue
        key, sep, value = line.partition(":")
        if not sep:
            pytest.fail(f"unparseable manifest line: {line!r}")
        key = key.strip()
        if key in data:
            pytest.fail(f"duplicate manifest key: {key!r}")
        value = value.strip()
        if value == "":
            current = []
            data[key] = current
        else:
            current = None
            data[key] = _scalar(value)
    return data


def _raw_value(key, path=MANIFEST):
    for line in path.read_text(encoding="utf-8").splitlines():
        head, sep, value = line.partition(":")
        if sep and head.strip() == key:
            return value.strip()
    return None


# ---------------------------------------------------------------------------
# Local catalog entry (plugin-catalog/ads-intel.yaml)
#
# R10-LOCAL: the entry is prepared locally only. The repo is not published and
# rule 5 (owner-or-major-contributor) is still pending, so no PR is opened.
#
# Field set mirrored from the real loader, not invented:
#   scripts/validate_plugin_catalog.py  -> KNOWN_KEYS / REQUIRED_KEYS
#   hermes_cli/plugin_catalog.py        -> PluginCatalogEntry
# Both live in the hermes-agent checkout. Two consequences worth knowing:
#   * ``license`` is NOT a catalog field (it is a plugin.yaml field). Adding it
#     to the entry earns an "unknown top-level key" warning at admission, so the
#     entry must not carry it; the license contract lives on the manifest side.
#   * ``repo``/``tier`` are required/meaningful there: tier must be community
#     (only Nous maintainers set official/verified).
# ---------------------------------------------------------------------------

CATALOG_ENTRY = ROOT / "plugin-catalog" / "ads-intel.yaml"

KNOWN_ENTRY_FIELDS = {
    "name",
    "repo",
    "sha",
    "subdir",
    "description",
    "maintainer",
    "tier",
    "category",
    "requires_hermes",
    "docs_url",
    "version",
    "image",
    "screenshots",
    "readme",
    "platforms",
    "capabilities",
    "title",
    "onboarding",
    "known_issues",
    "attested_binaries",
}
REQUIRED_ENTRY_FIELDS = {"name", "repo", "sha", "description", "maintainer"}
CAPABILITY_FIELDS = {"provides_tools", "provides_hooks", "provides_middleware", "requires_env"}

# Matches hermes_cli.plugin_catalog._SHA_RE, plus the "not a real pin" guard.
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PLACEHOLDERS = {"PLACEHOLDER", "TODO", "0" * 40, "f" * 40}


def load_catalog_entry(path=CATALOG_ENTRY):
    """Parse the catalog entry: top-level scalars plus one level of nesting.

    Only the shape the entry actually uses is supported (scalars at column 0,
    ``capabilities:`` as a two-column block of lists). Anything else fails
    loudly instead of being silently dropped.
    """
    data, section, section_key = {}, None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()

        if line[0] == " ":
            if section is None:
                pytest.fail(f"indented line outside a section: {line!r}")
            assert section is not None  # narrowing for type checkers
            if stripped.startswith("- "):
                if not (section_key and isinstance(section.get(section_key), list)):
                    pytest.fail(f"list item without a list key: {line!r}")
                section[section_key].append(_scalar(stripped[2:]))
                continue
            key, sep, value = stripped.partition(":")
            if not sep:
                pytest.fail(f"unparseable entry line: {line!r}")
            key = key.strip()
            if key in section:
                pytest.fail(f"duplicate entry key: {key!r}")
            value = value.strip()
            if value == "":
                section_key = key
                section[key] = []
            else:
                section_key = None
                section[key] = _scalar(value)
            continue

        key, sep, value = line.partition(":")
        if not sep:
            pytest.fail(f"unparseable entry line: {line!r}")
        key = key.strip()
        if key in data:
            pytest.fail(f"duplicate entry key: {key!r}")
        value = value.strip()
        section, section_key = None, None
        if value == "":
            section = {}
            data[key] = section
        else:
            data[key] = _scalar(value)
    return data


def test_catalog_entry_matches_manifest():
    assert CATALOG_ENTRY.is_file(), f"missing local catalog entry: {CATALOG_ENTRY}"
    entry = load_catalog_entry()
    m = load_manifest()

    # No invented fields: everything in the entry must exist in the real schema.
    unknown = set(entry) - KNOWN_ENTRY_FIELDS
    assert unknown == set(), f"key(s) unknown to the catalog loader: {sorted(unknown)}"
    missing = REQUIRED_ENTRY_FIELDS - set(entry)
    assert missing == set(), f"missing required catalog field(s): {sorted(missing)}"

    # Rule 2: a full 40-hex commit SHA, never a placeholder.
    # Deliberately not compared to ``git rev-parse HEAD``: committing this file
    # moves HEAD, and the pin is re-taken after the final commit at publication
    # time. Comparing to a live HEAD here would make the suite self-breaking.
    assert SHA_RE.match(entry["sha"] or ""), f"sha is not 40 lowercase hex: {entry['sha']!r}"
    assert entry["sha"] not in PLACEHOLDERS, "sha is still a placeholder"

    assert entry["name"] == "ads-intel" == m["name"]
    assert entry["version"] == m["version"], "version drift vs plugin.yaml"
    assert entry["requires_hermes"] == m["requires_hermes"], (
        "rule 14: the entry and plugin.yaml must declare the same floor"
    )

    # Rule 5 / publication: repo must be a cloneable https URL, tier community.
    assert entry["repo"].startswith("https://"), f"repo must be https: {entry['repo']!r}"
    assert entry["tier"] == "community"
    assert entry["maintainer"] == "felipauskas"
    assert entry["description"].strip()

    # license is a plugin.yaml field only; keeping it off the entry keeps the
    # admission validator warning-free. The manifest still has to be MIT.
    assert "license" not in entry, "license is not a catalog field (unknown-key warning)"
    assert m["license"] == "MIT"

    caps = entry["capabilities"]
    assert isinstance(caps, dict) and set(caps) <= CAPABILITY_FIELDS, (
        f"unknown capabilities key(s): {sorted(set(caps) - CAPABILITY_FIELDS)}"
    )
    assert set(caps["provides_tools"]) == set(m["provides_tools"]) == EXPECTED_TOOLS
    assert caps["provides_hooks"] == []
    assert caps["provides_middleware"] == []
    assert caps["requires_env"] == []

    assert entry["platforms"] == []  # empty = every OS


def test_manifest_declares_catalog_fields():
    m = load_manifest()

    assert set(m) - KNOWN_FIELDS == set(), (
        "unknown manifest field(s) ignored by Hermes: "
        f"{sorted(set(m) - KNOWN_FIELDS)}"
    )

    assert NAME_RE.match(m.get("name") or ""), f"invalid plugin name: {m.get('name')!r}"
    assert m.get("label")
    assert VERSION_RE.match(m.get("version") or ""), f"invalid version: {m.get('version')!r}"
    assert (_raw_value("version") or "")[:1] in "\"'", "version must be quoted (keep it a string)"

    assert isinstance(m.get("description"), str) and m["description"].strip()
    assert m.get("author")
    assert isinstance(m.get("license"), str) and m["license"].strip()
    # Rule 5: not published yet, so there is no homepage URL to point at.
    # Added at publication, together with the GitHub slug in the README.
    assert "homepage" not in m, (
        "plugin.yaml must not declare a homepage until the repo is published"
    )

    assert m.get("tags") == EXPECTED_TAGS
    assert m.get("requires_hermes"), "requires_hermes must declare a Hermes version range"
    assert m.get("manifest_version") == "2"
    assert m.get("capabilities") == []
    assert m.get("python_dependencies") == []
    assert set(m.get("provides_tools") or []) == EXPECTED_TOOLS

    registered = set(
        re.findall(r'ctx\.register_tool\(name="([^"]+)"', INIT.read_text(encoding="utf-8"))
    )
    assert registered == EXPECTED_TOOLS, f"declared tools drifted from __init__.py: {registered}"
