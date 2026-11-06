"""Manifest contract: the fields Hermes catalog admission requires.

Parsed with a tiny stdlib reader so the test suite stays dependency-free
(the plugin itself declares ``python_dependencies: []``).
"""

from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parent.parent / "plugin.yaml"

EXPECTED_TOOLS = {"ad_search", "ad_watch", "ad_check"}


def _scalar(raw):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [p.strip().strip("\"'") for p in inner.split(",")] if inner else []
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def load_manifest(path=MANIFEST):
    data, current = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current is None:
                pytest.fail(f"list item outside a key: {line!r}")
            assert current is not None  # narrowing for type checkers
            current.append(_scalar(stripped[2:]))
            continue
        key, sep, value = line.partition(":")
        if not sep:
            pytest.fail(f"unparseable manifest line: {line!r}")
        value = value.strip()
        if value == "":
            current = []
            data[key.strip()] = current
        else:
            current = None
            data[key.strip()] = _scalar(value)
    return data


def test_manifest_declares_catalog_fields():
    m = load_manifest()

    assert m.get("requires_hermes"), "requires_hermes must declare a Hermes version range"
    assert m.get("manifest_version") == "2"
    assert m.get("license")
    assert m.get("capabilities") == []
    assert m.get("python_dependencies") == []
    assert set(m.get("provides_tools") or []) == EXPECTED_TOOLS
