import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from diffing import diff_snapshots

OLD = {"ads": {"A1": {"id": "A1", "status": "active", "creative_text": "buy shoes"},
               "A2": {"id": "A2", "status": "active", "creative_text": "old copy"}}}
NEW = {"ads": {"A1": {"id": "A1", "status": "ended", "creative_text": "buy shoes"},
               "A2": {"id": "A2", "status": "active", "creative_text": "new copy"},
               "A3": {"id": "A3", "status": "active", "creative_text": "hello"}}}


def test_diff_classifies_all_changes():
    d = diff_snapshots(OLD, NEW)
    assert [a["id"] for a in d["new"]] == ["A3"]
    assert [a["id"] for a in d["ended"]] == ["A1"]
    assert [a["id"] for a in d["changed"]] == ["A2"]


def test_diff_empty_old_is_all_new():
    d = diff_snapshots({"ads": {}}, NEW)
    assert len(d["new"]) == 3 and not d["ended"] and not d["changed"]


def test_diff_no_changes():
    d = diff_snapshots(NEW, NEW)
    assert d == {"new": [], "ended": [], "changed": []}


def test_diff_revived_ad_is_new_not_changed():
    """An ad flipping ended -> active is `new`, never `changed`; a status that
    differs only by case/whitespace is not a change at all."""
    old = {"ads": {"R1": {"id": "R1", "status": "ended", "creative_text": "back again"},
                   "Q1": {"id": "Q1", "status": "active", "creative_text": "steady"}}}
    new = {"ads": {"R1": {"id": "R1", "status": "active", "creative_text": "back again"},
                   "Q1": {"id": "Q1", "status": "Active ", "creative_text": "steady"}}}
    d = diff_snapshots(old, new)
    assert [a["id"] for a in d["new"]] == ["R1"]
    assert d["changed"] == []
    assert d["ended"] == []


def test_diff_all_ads_ended():
    """Every ad present in old and absent from new is reported as ended."""
    d = diff_snapshots(OLD, {"ads": {}})
    assert sorted(a["id"] for a in d["ended"]) == ["A1", "A2"]
    assert d["new"] == [] and d["changed"] == []

def test_diff_detects_destination_and_cta_changes():
    old = {"ads": {"D1": {"id": "D1", "status": "active", "creative_text": "x",
                          "link_url": "https://a.example/", "link_title": "A",
                          "cta_text": "Shop Now"}}}
    for key, value in (
        ("link_url", "https://b.example/"),
        ("link_title", "B"),
        ("cta_text", "Learn More"),
    ):
        new = {"ads": {"D1": {**old["ads"]["D1"], key: value}}}
        d = diff_snapshots(old, new)
        assert [a["id"] for a in d["changed"]] == ["D1"], key
        assert d["new"] == [] and d["ended"] == []


def test_diff_ignores_fields_absent_from_old_snapshot():
    """Enriched fields added after a baseline was written must not make every
    ad look changed on the first run after the upgrade."""
    old = {"ads": {"L1": {"id": "L1", "status": "active", "creative_text": "x"}}}
    new = {"ads": {"L1": {"id": "L1", "status": "active", "creative_text": "x",
                          "link_url": "https://a.example/", "link_title": "A",
                          "cta_text": "Shop Now"}}}
    assert diff_snapshots(old, new) == {"new": [], "ended": [], "changed": []}


def test_diff_compares_enriched_fields_when_both_sides_have_them():
    old = {"ads": {"E1": {"id": "E1", "status": "active", "creative_text": "x",
                          "link_url": "", "link_title": "", "cta_text": ""}}}
    new = {"ads": {"E1": {"id": "E1", "status": "active", "creative_text": "x",
                          "link_url": "", "link_title": "", "cta_text": ""}}}
    assert diff_snapshots(old, new)["changed"] == []


def test_diff_ignores_like_counter_churn_in_link_title():
    """A re-render that only moves the page's like counter is not a change.

    ``link_title`` can carry the public render's live "N people like this"
    line (e.g. a Like-Page CTA block). Comparing it byte-for-byte made a
    counter-only re-render look like a creative change, so the counter span is
    normalised out before comparison.
    """
    base = {"id": "L1", "status": "active", "creative_text": "x",
            "link_url": "https://a.example/", "cta_text": "Learn More"}
    variants = [
        "McDonald's Interest 19,720,345 people like this",
        "McDonald's Interest 19,720,350 people like this",
        "McDonald's Interest 19.8M people like this",
        "McDonald's Interest",
    ]
    old = {"ads": {"L1": {**base, "link_title": variants[0]}}}
    for title in variants[1:]:
        new = {"ads": {"L1": {**base, "link_title": title}}}
        assert diff_snapshots(old, new)["changed"] == [], title


def test_diff_still_reports_real_link_title_change_with_counter():
    """Stripping the counter must not swallow the rest of the title."""
    old = {"ads": {"L1": {"id": "L1", "status": "active", "creative_text": "x",
                          "link_title": "Shop shoes 1,000 people like this"}}}
    new = {"ads": {"L1": {"id": "L1", "status": "active", "creative_text": "x",
                          "link_title": "Shop boots 1,100 people like this"}}}
    d = diff_snapshots(old, new)
    assert [a["id"] for a in d["changed"]] == ["L1"]


def test_diff_tolerates_malformed_snapshot_payloads():
    """A corrupt snapshot (None, or {"ads": "notadict"}) is empty, not a crash.

    On-disk JSON is hand-editable; a bad ``ads`` value must degrade to "no ads"
    so the check still runs instead of being lost to AttributeError.
    """
    assert diff_snapshots(None, {"ads": {}}) == {"new": [], "ended": [], "changed": []}
    assert diff_snapshots({"ads": "notadict"}, {"ads": {}}) == {
        "new": [], "ended": [], "changed": []
    }
    assert diff_snapshots([], {"ads": {}}) == {"new": [], "ended": [], "changed": []}
    # A corrupt *new* side means every old id is absent: the same "all ended"
    # result an explicit empty listing gives.
    d = diff_snapshots(OLD, {"ads": "notadict"})
    assert sorted(a["id"] for a in d["ended"]) == ["A1", "A2"]
    assert d["new"] == [] and d["changed"] == []


def test_diff_skips_non_dict_ad_values():
    """Junk values inside an otherwise valid ads map are ignored, not compared."""
    old = {"ads": {"A1": {"id": "A1", "status": "active"},
                   "J": "not-an-ad", "N": None}}
    new = {"ads": {"A1": {"id": "A1", "status": "active"},
                   "J2": ["junk"]}}
    assert diff_snapshots(old, new) == {"new": [], "ended": [], "changed": []}


# --- F3: partial renders must not report hydration losses as changes --------


def _ad(ad_id="H1", **extra):
    return {"id": ad_id, "status": "active", "creative_text": "buy shoes", **extra}


def test_partial_render_losing_cta_and_title_is_not_a_change():
    """A re-render that never hydrated the CTA block leaves blanks.

    Those blanks are unknown values, not a creative edit, so a partial diff
    must not report the ad as changed (and so must not poison the baseline).
    """
    old = {"ads": {"H1": _ad(link_url="https://a.example/",
                             link_title="Shop", cta_text="Shop Now")}}
    new = {"ads": {"H1": _ad(link_url="https://a.example/",
                             link_title="", cta_text="")}}
    assert diff_snapshots(old, new, partial=True) == {
        "new": [], "ended": [], "changed": []
    }


def test_partial_render_losing_creative_text_is_not_a_change():
    old = {"ads": {"H1": _ad()}}
    new = {"ads": {"H1": {**_ad(), "creative_text": ""}}}
    assert diff_snapshots(old, new, partial=True)["changed"] == []


def test_complete_render_losing_cta_is_still_a_change():
    """On a complete render an empty field is an observation, not a gap.

    ``partial=False`` (the default) keeps the existing rule: an empty field
    that was populated before is a real edit, because the render finished and
    the field is genuinely absent from the creative.
    """
    old = {"ads": {"H1": _ad(link_title="Shop", cta_text="Shop Now")}}
    new = {"ads": {"H1": _ad(link_title="", cta_text="")}}
    assert [a["id"] for a in diff_snapshots(old, new)["changed"]] == ["H1"]
    assert [a["id"] for a in diff_snapshots(
        old, new, partial=False
    )["changed"]] == ["H1"]


def test_partial_render_real_title_change_is_still_a_change():
    """Both sides populated: a genuine title edit is reported even on partial."""
    old = {"ads": {"H1": _ad(link_title="Shop shoes")}}
    new = {"ads": {"H1": _ad(link_title="Shop boots")}}
    assert [a["id"] for a in diff_snapshots(old, new, partial=True)["changed"]] == ["H1"]


def test_partial_flag_leave_status_transitions_intact():
    old = {"ads": {"H1": {**_ad(), "status": "active", "cta_text": "Shop Now"}}}
    new = {"ads": {"H1": {**_ad(), "status": "ended", "cta_text": ""}}}
    d = diff_snapshots(old, new, partial=True)
    assert [a["id"] for a in d["ended"]] == ["H1"]
    assert d["changed"] == []


# --- F3: a partial render cannot prove an ad ended ---------------------------


def test_partial_render_missing_id_is_not_ended():
    """An id absent from a clipped render is unknown, not stopped.

    A partial render never reached the card, so diffing it unfiltered would
    fabricate an ending for every id past the clip.
    """
    old = {"ads": {"A1": _ad("A1"), "A2": _ad("A2")}}
    new = {"ads": {"A1": _ad("A1")}}
    assert diff_snapshots(old, new, partial=True)["ended"] == []
    # Nothing else is invented either: A1 is unchanged.
    assert diff_snapshots(old, new, partial=True) == {
        "new": [], "ended": [], "changed": []
    }


def test_complete_render_missing_id_is_still_ended():
    """On an unclipped render a missing id remains the `ended` bucket."""
    old = {"ads": {"A1": _ad("A1"), "A2": _ad("A2")}}
    new = {"ads": {"A1": _ad("A1")}}
    assert [a["id"] for a in diff_snapshots(old, new)["ended"]] == ["A2"]
    assert [a["id"] for a in diff_snapshots(old, new, partial=False)["ended"]] == [
        "A2"
    ]


def test_partial_status_flip_survives_ended_suppression():
    """A status flip is observed on a rendered card, not inferred from absence."""
    old = {"ads": {"A1": _ad("A1"), "A2": _ad("A2")}}
    new = {"ads": {"A1": {**_ad("A1"), "status": "inactive"}}}
    d = diff_snapshots(old, new, partial=True)
    assert [a["id"] for a in d["ended"]] == ["A1"]
    # A2 is absent from the partial render: not reported at all.
    assert all(a["id"] != "A2" for a in d["ended"])
