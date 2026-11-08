"""Adversarial probe for ads-intel EVAL C. Read-only: no source changes.

Verification is structural: the report HTML is parsed with html.parser and the
tag/attribute tree is inspected (no <script>/<img>, no on* handlers, href only
http(s)), and decoded text is compared byte-for-byte with the input payload.
"""
import json, time, sys, os, tempfile, re
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, "/Users/felipevleon/coding-projects/ads-intel")
import report, sources, tools, store, diffing

RESULTS = []
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "div", "span",
                "header", "h1", "a", "p"}
FORBIDDEN_TAGS = {"script", "img", "iframe", "object", "embed", "svg", "math",
                  "link", "base", "form", "input", "video", "audio", "source", "template"}


class Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attrs = []          # (tag, name, value)
        self.text = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        for n, v in attrs:
            self.attrs.append((tag, n, v))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        self.text.append(data)


def audit(html):
    a = Audit()
    a.feed(html)
    errs = []
    bad_tags = FORBIDDEN_TAGS.intersection(a.tags)
    if bad_tags:
        errs.append(f"forbidden tags {sorted(bad_tags)}")
    for tag, name, value in a.attrs:
        ln = (name or "").lower()
        if ln.startswith("on"):
            errs.append(f"event handler {tag}[{name}]")
        if ln in ("src", "srcset", "formaction", "action", "background", "poster"):
            errs.append(f"resource attr {tag}[{name}]={value!r}")
        if ln == "href":
            v = (value or "").strip().lower()
            if not v.startswith(("http://", "https://")):
                errs.append(f"non-http href {value!r}")
        if ln == "style" and re.search(r"expression|url\s*\(|javascript:", value or "", re.I):
            errs.append(f"dangerous style {value!r}")
    if re.search(r"<\s*(script|img|iframe|svg|object|embed)\b", html, re.I):
        errs.append("raw executable tag in bytes")
    return errs


def record(case, payload, expect, passed, detail=""):
    RESULTS.append({"case": case, "input": payload, "expect": expect,
                    "pass": bool(passed), "detail": detail})


def ad(i, **over):
    a = {"id": str(i), "page_name": "Nike", "status": "active",
         "first_seen": "May 1, 2026", "last_seen": "Jun 1, 2026",
         "creative_text": "Just do it", "library_url": f"https://www.facebook.com/ads/library/?id={i}",
         "page_url": f"https://www.facebook.com/{i}", "page_id": str(i),
         "link_url": "https://example.com", "link_title": "Example",
         "cta_text": "Shop", "images": [], "has_video": False,
         "same_creative_count": 0, "multiple_versions": False}
    a.update(over)
    return a


def render(ads, diff=None, meta=None, query="nike", country="US", advertiser=""):
    return report.build_html(query, diff or {"new": list(ads.values())}, ads,
                             meta or {"checked_at": "2026-11-06T12:00:00", "partial": False},
                             country=country, advertiser=advertiser)


PAYLOADS = [
    '<script>alert(1)</script>',
    '"><script>alert(document.domain)</script>',
    "' onmouseover='alert(1)",
    '<img src=x onerror=alert(1)>',
    '"><img src=x onerror=alert(1)>',
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'java\tscript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    '"><svg/onload=alert(1)>',
    '&lt;script&gt;alert(1)&lt;/script&gt;',
    '</title><script>alert(1)</script>',
    '</style><script>alert(1)</script>',
    '<!--<script>alert(1)</script>-->',
    '\u2028\u2029<script>alert(1)</script>',
]

TEXT_KEYS = ("page_name", "creative_text", "status", "first_seen", "last_seen")

# ---------- A. XSS in every text field, structural audit ----------
for key in TEXT_KEYS:
    for p in PAYLOADS:
        html = render({"1": ad(1, **{key: p})})
        errs = audit(html)
        record(f"A.{key}", repr(p), "parsed tree has no script/img/on*/js: URL", not errs,
               "; ".join(errs) if errs else "escaped text only")

# ---------- A2. exact text round-trip (no double-escape / truncation) ----------
for key in TEXT_KEYS:
    for p in ['<script>alert(1)</script>', 'A&B "q" \'x\'', '</title>']:
        html = render({"1": ad(1, **{key: p})})
        a = Audit(); a.feed(html)
        joined = "".join(a.text)
        record(f"A2.{key}", repr(p), "decoded page text contains payload verbatim",
               p in joined, "round-trips" if p in joined else repr(joined[-120:]))

# ---------- B. URL fields: only http(s) reaches href ----------
for key in ("library_url", "link_url"):
    for p in ["javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)",
              "java\tscript:alert(1)", "data:text/html,<script>alert(1)</script>",
              "vbscript:msgbox(1)", "//evil.example/x", "/\\evil.example",
              "http://ok.example/?q=<script>", "https://ok.example/\"><script>alert(1)</script>"]:
        a = ad(1); a[key] = p
        html = render({"1": a})
        errs = audit(html)
        # attribute value must round-trip to the URL exactly when http(s)
        hrefs = [v for t, n, v in Audit().tags and [] or []]
        au = Audit(); au.feed(html)
        hrefs = [v for t, n, v in au.attrs if n == "href" and t == "a"]
        if p.strip().lower().startswith(("http://", "https://")):
            ok = not errs and p.strip() in hrefs
        else:
            ok = not errs and not any("evil" in h or "javascript" in h.lower() or "data:" in h.lower()
                                      or "vbscript" in h.lower() for h in hrefs)
        record(f"B.{key}", repr(p), "href http(s) only; value exact", ok,
               f"hrefs={hrefs[:2]} errs={errs}")

# page_url is not rendered today; assert it never becomes an attribute
a = ad(1, page_url='javascript:alert(1)')
html = render({"1": a})
au = Audit(); au.feed(html)
record("B.page_url", "'javascript:alert(1)'", "page_url not emitted as href",
       all("javascript" not in (v or "").lower() for t, n, v in au.attrs if n == "href"), "")

# ---------- C. id and attribute injection ----------
for p in ['1" onmouseover="alert(1)', '<script>alert(1)</script>', '1"><img src=x>', '"><svg onload=1>']:
    html = render({p: ad(p)})
    errs = audit(html)
    au = Audit(); au.feed(html)
    ids = [v for t, n, v in au.attrs if n == "data-ad-id"]
    record("C.id", repr(p), "data-ad-id decodes to the id verbatim",
           not errs and ids == [p], f"ids={ids} errs={errs}")

# ---------- D. country / query URL injection ----------
COUNTRY_BAD = ["US&q=evil", "us", "U1", "USA", "U S", "US\n", "US\x00", "", None, 1, ["US"], "ＵＳ", "US;"]
for c in COUNTRY_BAD:
    try:
        url = sources.build_url("nike", country=c)
        record("D.build_url", repr(c), "ValueError invalid_country", False, f"built {url!r}")
    except ValueError as e:
        record("D.build_url", repr(c), "ValueError invalid_country", str(e) == "invalid_country", str(e))
    except Exception as e:
        record("D.build_url", repr(c), "ValueError invalid_country", False, f"{type(e).__name__}: {e}")

for c in ["US&q=evil", "USA", "U1"]:
    out = json.loads(tools.ad_search({"query": "nike", "country": c}))
    record("D.ad_search", repr(c), "error invalid_country",
           out.get("error") == "invalid_country", json.dumps(out)[:120])
out = json.loads(tools.ad_search({"query": "nike", "country": "us"}))
record("D.ad_search", repr("us"), "lowercase normalizes to US, not invalid_country",
       out.get("error") != "invalid_country" and out.get("country", "US") in ("US", None), json.dumps(out)[:120])
out = json.loads(tools.ad_search({"query": "nike", "country": None}))
record("D.ad_search", "None", "null treated as absent (US), gets fetch error not invalid_country",
       out.get("error") != "invalid_country", json.dumps(out)[:120])

for q in ["nike&country=XX", "a b+c", "%00", "nike#frag", "nike?x=1", "nike\r\nX: y", "nike'/x"]:
    url = sources.build_url(q, country="US")
    qs = parse_qs(urlsplit(url).query, keep_blank_values=True)
    ok = qs.get("country") == ["US"] and qs.get("q") == [q]
    record("D.query", repr(q), "q percent-encoded; country stays US", ok, url)

# active_status / media_type vocabulary
for key, bad in (("active_status", "active&country=XX"), ("media_type", "video&x=1"),
                 ("active_status", "ACTIVE"), ("media_type", "")):
    try:
        sources.build_url("nike", **{key: bad})
        record(f"D.{key}", repr(bad), "ValueError invalid_<field>", False, "accepted")
    except ValueError as e:
        record(f"D.{key}", repr(bad), "ValueError invalid_<field>", str(e) == f"invalid_{key}", str(e))

# ---------- E. huge / pathological inputs ----------
big_text = "A" * 2_000_000
t0 = time.perf_counter(); html = render({"1": ad(1, creative_text=big_text)}); dt = time.perf_counter() - t0
record("E.huge_text", "creative_text 2,000,000 chars", "renders without crash", "<div class=\"copy\">" in html,
       f"{dt:.2f}s, {len(html)} bytes")

big_ads = {str(i): ad(i) for i in range(20000)}
t0 = time.perf_counter(); html = render(big_ads, {"new": list(big_ads.values())}); dt = time.perf_counter() - t0
record("E.huge_count", "20,000 ads", "all cards present", html.count("data-ad-id=") == 20000,
       f"{dt:.2f}s, {len(html)} bytes")

huge_id = "9" * 100000
html = render({huge_id: ad(1, id=huge_id)})
record("E.huge_id", "id 100,000 digits", "renders without crash", "data-ad-id=" in html, f"{len(html)} bytes")

html = render({"1": ad(1, creative_text="<div>" * 5000)})
record("E.nested_markup", "'<div>' x 5000", "every tag escaped", html.count("&lt;div&gt;") == 5000, "")

html = render({"1": ad(1, page_name="|" * 300000, creative_text="|" * 300000)})
record("E.600kb_pipes", "300k chars in two fields", "no crash, bounded output", len(html) < 5_000_000, f"{len(html)} bytes")

# ---------- F. malformed payloads ----------
MALFORMED = [
    "{not json", '{"results": [{"content": ', "[]", "[1,2,3]", '["a","b"]', "[null,null]",
    '[{"foo": "bar"}]', "{}", '{"results": []}', '{"results": "nope"}', '{"results": [null]}',
    '{"results": [{"content": null}]}', '{"content": 123}', '"just a string"', "null", "true", "12345",
    '{"results": [{"error": "<script>alert(1)</script>"}]}',
]
def dispatch_factory(payload):
    return lambda name, args: payload
for p in MALFORMED:
    try:
        out, meta = sources.fetch_ads_with_meta("nike", limit=20, dispatch=dispatch_factory(p))
        record("F.malformed", p[:70], "raises FetchError/ParseError, never returns junk", False,
               f"returned {len(out)} ads")
    except (sources.FetchError, sources.ParseError) as e:
        record("F.malformed", p[:70], "raises FetchError/ParseError, never returns junk", True,
               f"{type(e).__name__}: {str(e)[:80]}")
    except Exception as e:
        record("F.malformed", p[:70], "raises FetchError/ParseError, never returns junk", False,
               f"UNEXPECTED {type(e).__name__}: {e}"[:120])

# transport shapes: None / tuple / int / generator
for p in [None, 42, (1, 2), object()]:
    try:
        sources.fetch_ads_with_meta("nike", dispatch=(lambda x: (lambda n, a: x))(p))
        record("F.transport", type(p).__name__, "FetchError, no crash", False, "accepted")
    except sources.FetchError as e:
        record("F.transport", type(p).__name__, "FetchError, no crash", True, str(e)[:60])
    except Exception as e:
        record("F.transport", type(p).__name__, "FetchError, no crash", False, f"{type(e).__name__}: {e}")

# hostile JSON ad object
hostile_ad = {"id": "1", "page_name": "<script>alert(1)</script>",
              "library_url": "javascript:alert(1)", "link_url": "javascript:alert(1)",
              "images": ["javascript:alert(1)", "https://ok/x.png", 5, None],
              "page_id": "<script>", "same_creative_count": "abc",
              "multiple_versions": "false", "has_video": "false"}
ads_out, meta = sources.fetch_ads_with_meta("nike", limit=20,
                                            dispatch=dispatch_factory(json.dumps([hostile_ad])))
a = ads_out[0]
record("F.hostile_json", json.dumps(hostile_ad)[:140],
       "URLs http(s) only, page_id digits, flags strict, count numeric",
       a["library_url"].startswith("https://www.facebook.com/ads/library/") and a["link_url"] == ""
       and a["page_id"] == "" and a["images"] == ["https://ok/x.png"]
       and a["same_creative_count"] == 0 and a["multiple_versions"] is False and a["has_video"] is False,
       json.dumps({k: a[k] for k in ("library_url", "link_url", "page_id", "images",
                                     "same_creative_count", "multiple_versions", "has_video")}))

# id types in JSON ads
for rid in [None, "", 0, False, [], {}, "  "]:
    try:
        ads_out, _ = sources.fetch_ads_with_meta("nike", dispatch=dispatch_factory(json.dumps([{"id": rid, "page_name": "x"}])))
        record("F.id_type", repr(rid), "skipped or stringified, never crash", True, f"{len(ads_out)} ads")
    except (sources.FetchError, sources.ParseError) as e:
        record("F.id_type", repr(rid), "skipped or stringified", True, type(e).__name__)
    except Exception as e:
        record("F.id_type", repr(rid), "skipped or stringified", False, f"{type(e).__name__}: {e}")

# ---------- G. non-dict ads / malformed diff/meta structures ----------
html = report.build_html("q", {"new": ["<script>alert(1)</script>", None, 5, {"id": "1", **ad(1)}]},
                         {"1": ad(1), "2": "not a dict", "3": None, "4": 42}, {"checked_at": "x"})
record("G.non_dict_diff", '"new": [str, None, int, dict]; ads mapping has str/None/int',
       "non-dicts skipped, one card, no crash", html.count("data-ad-id=") == 1 and not audit(html), "")

for bad_diff in [{"new": "abc"}, {"new": {"a": 1}}, {"new": None}, {"new": 42}, {"new": [{"id": None}]},
                 None, [], "str"]:
    try:
        h = report.build_html("q", bad_diff, {"1": ad(1)}, {"checked_at": "x"})
        ok = h.count("data-ad-id=") == 1
    except Exception as e:
        ok, h = False, f"{type(e).__name__}: {e}"
    record("G.diff_shape", repr(bad_diff)[:60], "non-list bucket empty; no crash", ok, "")

for bad_meta in [None, {}, {"partial": "false"}, {"partial": "true"}, {"checked_at": None},
                 {"partial": []}, {"partial": {"x": 1}}]:
    try:
        h = report.build_html("q", {}, {"1": ad(1)}, bad_meta)
        ok = "data-ad-id=" in h
        if bad_meta == {"partial": "false"}:
            ok = ok and "Partial listing" not in h
    except Exception as e:
        ok = False
    record("G.meta_shape", repr(bad_meta), "no crash; partial only when truthy", ok, "")

d = report.build_digest("<script>", {"new": "x"}, {"1": "junk", "2": ad(2)}, {"checked_at": None})
record("G.digest", "non-dict ads + string bucket", "counts lenient", d["total"] == 1 and d["new"] == 0, json.dumps(d))

# ---------- H. fail-safe diffs / corrupt state ----------
old_d = {"ads": {"1": ad(1), "2": ad(2)}}
new_d = {"ads": {"1": ad(1, status="inactive"), "3": ad(3)}}
diff = diffing.diff_snapshots(old_d, new_d)
record("H.status_flip", "1 active->inactive, 2 gone, 3 new", "ended={1,2}, new={3}",
       sorted(x["id"] for x in diff["ended"]) == ["1", "2"] and [x["id"] for x in diff["new"]] == ["3"],
       f"new={[x['id'] for x in diff['new']]} ended={[x['id'] for x in diff['ended']]}")

diff = diffing.diff_snapshots({"ads": {"1": ad(1), "2": "junk"}},
                              {"ads": {"1": ad(1), "3": None}})
record("H.non_dict_snapshot", "ads mapping holds string/None", "no crash",
       True, f"new={len(diff['new'])} ended={len(diff['ended'])}")

for shape in [{"ads": "notadict"}, {"ads": None}, {}, None]:
    try:
        diff = diffing.diff_snapshots(shape, {"ads": {}})
        ok = isinstance(diff, dict)
    except Exception as e:
        ok = False
    record("H.diff_shape", repr(shape), "no crash (or documented raise)", ok, "")

# corrupt snapshot files
tmp = tempfile.mkdtemp()
os.environ["HOME"] = tmp
import importlib
importlib.reload(store)
sp = store._snapshot_path("q")
sp.parent.mkdir(parents=True, exist_ok=True)
for content in ["{bad json", "[]", "null", '"str"', '{"ads": "notadict"}',
                '{"ads": {"1": "junk"}}', '{"ads": {"1": {"id": "1"}}, "advertiser": 5}']:
    sp.write_text(content)
    try:
        loaded = store.load_snapshot("q")
        ok = isinstance(loaded, dict)
    except Exception as e:
        ok = False; loaded = f"{type(e).__name__}: {e}"
    record("H.corrupt_snapshot", content[:44], "loads dict, never raises", ok, json.dumps(loaded)[:100])

wp = store._watch_path(); wp.parent.mkdir(parents=True, exist_ok=True)
for content in ["{bad", '{"a":1}', "[1,null,\"x\",{}]", '[" "]', '[[1]]']:
    wp.write_text(content)
    try:
        out = store.watch_list()
        ok = isinstance(out, list) and all(isinstance(x, dict) for x in out)
    except Exception as e:
        ok, out = False, f"{type(e).__name__}: {e}"
    record("H.corrupt_watchlist", content[:36], "list of dicts, never raises", ok, json.dumps(out)[:100])

# prompt/template-injection strings in query must not alter markup structure
for q in ["{{7*7}}", "${jndi:ldap://x}", "{% debug %}", "../" * 3 + "etc/passwd", "\x00"]:
    h = render({"1": ad(1)}, {"new": [ad(1)]}, {"checked_at": "x"}, query=q)
    record("H.query_template", repr(q), "rendered as escaped text only", not audit(h), "")

# ---------- I. tool layer argument abuse ----------
CASES = [
    ("ad_search", {}), ("ad_search", {"query": ""}), ("ad_search", {"query": "x", "limit": "abc"}),
    ("ad_search", {"query": "x", "limit": -5}), ("ad_search", {"query": "x", "limit": 1e309}),
    ("ad_search", {"query": "x", "active_status": "bogus"}),
    ("ad_search", {"query": "x", "media_type": "bogus"}),
    ("ad_search", {"query": None}), ("ad_search", {"query": ["<script>"]}),
    ("ad_search", {"query": "x", "country": "US&q=evil"}),
    ("ad_watch", {"action": "add", "query": "x", "country": "US&q=evil"}),
    ("ad_watch", {"action": "add"}), ("ad_watch", {"action": "nuke"}),
    ("ad_watch", {"action": None}), ("ad_watch", {}),
]
for fn, args in CASES:
    try:
        out = json.loads(getattr(tools, fn)(args))
        record(f"I.{fn}", repr(args)[:90], "JSON dict, no exception", isinstance(out, dict),
               json.dumps(out)[:110])
    except Exception as e:
        record(f"I.{fn}", repr(args)[:90], "JSON dict, no exception", False, f"{type(e).__name__}: {e}")

# ---------- J. whole-report sweep ----------
evil = {str(i): ad(i, **{k: p for k in TEXT_KEYS}) for i, p in enumerate(PAYLOADS)}
html = render(evil, {"new": list(evil.values())},
              meta={"checked_at": "<script>alert(1)</script>", "partial": "x"})
errs = audit(html)
record("J.full_report", "all 16 payloads in every text field + checked_at",
       "structurally clean, no external resources", not errs,
       f"{len(html)} bytes; {errs}")
record("J.no_external", "full report", "zero <script>/<img>/src/link tags",
       not ({"script", "img", "link", "iframe", "object", "embed"} & set(audit(html) or []))
       and all(t not in html.lower() for t in ("<script", "<img", "<iframe", "<link ")), "")

# end-to-end: report written to disk and re-read
out = tempfile.mkdtemp()
paths = report.write_report("<script>alert(1)</script>", {"new": list(evil.values())},
                            evil, {"checked_at": "<img onerror=1>", "partial": False}, out)
disk = open(paths["html"], encoding="utf-8").read()
digest = json.load(open(paths["digest"], encoding="utf-8"))
record("J.write_report", "query + checked_at hostile, 16 evil ads",
       "disk HTML clean; digest valid JSON", not audit(disk) and isinstance(digest, dict),
       f"{len(disk)} bytes; digest keys={sorted(digest)[:6]}")

# ---------- K. numeric-field abuse ----------
for label, v in [("float('inf')", float("inf")), ("float('nan')", float("nan")),
                 ("10**5000", 10**5000), ("'9'*5000", "9" * 5000),
                 ("{'x':1}", {"x": 1}), ("[1,2]", [1, 2]), ("True", True)]:
    try:
        h = report.build_html("q", {}, {"1": ad(1, same_creative_count=v)}, {"checked_at": "x"})
        record("K.same_creative_count", label, "renders without crash", True, f"{len(h)} bytes")
    except Exception as e:
        record("K.same_creative_count", label, "renders without crash", False,
               f"{type(e).__name__}: {str(e)[:80]}")

# JSON literal 1e999 parses to inf
try:
    raw = json.loads('{"id":"1","page_name":"x","status":"active","same_creative_count":1e999}')
    h = report.build_html("q", {}, {"1": raw}, {"checked_at": "x"})
    record("K.json_inf", "same_creative_count: 1e999", "renders without crash", True, "")
except Exception as e:
    record("K.json_inf", "same_creative_count: 1e999", "renders without crash", False,
           f"{type(e).__name__}: {str(e)[:80]}")

passed = sum(1 for r in RESULTS if r["pass"])
json.dump({"total": len(RESULTS), "passed": passed,
           "failed": [r for r in RESULTS if not r["pass"]], "all": RESULTS},
          open("/Users/felipevleon/.hermes/profiles/partner/cache/scratch/adv_out.json", "w"), indent=1)
print("total", len(RESULTS), "passed", passed, "failed", len(RESULTS) - passed)
for r in RESULTS:
    if not r["pass"]:
        print("FAIL", r["case"], r["input"], "->", r["detail"][:300])
