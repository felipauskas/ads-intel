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
    assert (m.get("homepage") or "").startswith("https://")

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
