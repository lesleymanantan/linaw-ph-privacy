"""The local page and the glossary file."""
import csv
import json
import re
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from ph_privacy_guide import catalogue, glossary
from ph_privacy_guide.answer import labels
from ph_privacy_guide.app import web
from ph_privacy_guide.config import (BLOCK_HEADINGS, BLOCK_PENDING, BLOCK_SUMMARY, CONTACT_URL, LISTED_LABEL, ROOT, WEB_HOST)
from ph_privacy_guide.retrieve.search import SearchResult

CHUNK = {"citation": "<Cite> s.1", "authority": "rule", "status": "unverified", "date_issued": "2020-01-01",
         "page_start": 1, "page_end": 2, "warnings": ["A <warning>"], "text": "Exact <text>\nsecond line",
         "annotations": [{"number": 1, "text": "A note"}], "notes": ["A plain note"]}


class FakeSearcher:
    def search(self, query, k):
        if query == "unsure":
            return SearchResult([], [SimpleNamespace(chunk=CHUNK, score=1, matched=[])], True, "the reason")
        hit = SimpleNamespace(chunk=CHUNK, score=1, matched=[])
        side = [("pending", hit), ("summary", hit)] if query == "sides" else []
        return SearchResult([query], [hit], False, "", side=side, calibrated=query == "calibrated")


@pytest.fixture()
def base_url():
    server = web.make_server(FakeSearcher(), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://{WEB_HOST}:{server.server_port}"
    server.shutdown()
    server.server_close()


def _get(url, host=None):
    request = urllib.request.Request(url, headers={"Host": host} if host else {})
    with urllib.request.urlopen(request, timeout=5) as r:
        return r.status, r.read().decode(), dict(r.headers)


def test_binds_to_loopback_only():
    assert WEB_HOST == "127.0.0.1"
    server = web.make_server(FakeSearcher(), port=0)
    assert server.socket.getsockname()[0] == "127.0.0.1"
    server.server_close()


def test_home_page_has_question_box_and_limit(base_url):
    status, body, _ = _get(base_url + "/")
    assert status == 200 and 'name="q"' in body and "Not legal advice" in body


def test_results_show_citation_tag_status_warning_and_escape_text(base_url):
    _, body, _ = _get(base_url + "/?q=term")
    for needle in ("&lt;Cite&gt; s.1", "Type: Binding rule", "Status: not verified", "Source: &lt;Cite&gt; s.1, pages 1-2 (issued 1 Jan 2020)", "A &lt;warning&gt;", "Exact &lt;text&gt;\nsecond line", "NPC annotation 1"):
        assert needle in body
    assert "<Cite>" not in body


def test_not_sure_shows_contact_link_and_no_passage(base_url):
    _, body, _ = _get(base_url + "/?q=unsure")
    assert "Not sure" in body and f'<a href="{CONTACT_URL}">' in body
    assert "Exact" not in body


def test_side_blocks_have_their_own_headings_below_the_main_results(base_url):
    _, body, _ = _get(base_url + "/?q=sides")
    assert body.index("Pending change: draft, not law") > body.index("1. &lt;Cite&gt;")
    assert body.index("NPC summary, not the rule text") > body.index("Pending change")


def test_page_title_and_heading(base_url):
    body = _get(base_url + "/")[1]
    assert "<title>Linaw - PH Privacy Guide</title>" in body and "<h1>Linaw - PH Privacy Guide</h1>" in body


BANNER_EN = "Linaw does not yet check whether results answer your question. Read them carefully."
BANNER_FIL = "Hindi pa sinusuri ng Linaw kung sumasagot ang mga resulta sa iyong tanong. Basahin ito nang mabuti."


def test_the_banner_follows_the_page_language(base_url):
    en = _get(base_url + "/?q=term&lang=en")[1]
    fil = _get(base_url + "/?q=term&lang=fil")[1]
    assert BANNER_EN in en and BANNER_FIL not in en
    assert BANNER_FIL in fil and BANNER_EN not in fil
    assert "<title>Linaw - PH Privacy Guide</title>" in fil and "<h1>Linaw - PH Privacy Guide</h1>" in fil


def test_page_says_when_not_sure_is_switched_off(base_url):
    banner = "Linaw does not yet check whether results answer your question. Read them carefully."
    assert banner in _get(base_url + "/?q=term")[1].replace("&quot;", '"')
    assert banner not in _get(base_url + "/?q=calibrated")[1].replace("&quot;", '"')
    assert "A plain note" in _get(base_url + "/?q=term")[1]


def test_query_is_escaped(base_url):
    _, body, _ = _get(base_url + "/?q=%22%3E%3Cscript%3E")
    assert "<script>" not in body


def test_no_external_assets_or_scripts(base_url):
    _, body, headers = _get(base_url + "/?q=unsure")
    assert "<script" not in body and "<img" not in body and "<link" not in body and "@import" not in body
    assert re.findall(r"https?://[^\s\"<]+", body) == [CONTACT_URL, CONTACT_URL]
    assert "default-src 'none'" in headers["Content-Security-Policy"]


def test_other_host_header_is_refused(base_url):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base_url + "/", host="example.invalid")
    assert e.value.code == 403


def test_glossary_rows_have_english_sources_and_filled_terms_have_a_source():
    path = ROOT / "data" / "glossary" / "en_fil_terms.csv"
    if not path.exists():
        pytest.skip("run scripts/build_glossary.py first")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows and all(r["en_term"] and r["en_source_chunk_id"] for r in rows)
    for r in rows:
        assert r["fil_source"] or not r["fil_term"], r["en_term"]
    assert glossary.validate_rows(rows) == []
    assert all("DRAFT" not in r["en_source_citation"] for r in rows)


BASE = {"citation": "NPC Circular 2022-04, s.10", "authority": "rule", "status": "listed_no_repeal", "kind": "section",
        "date_issued": "2022-12-05", "page_start": 7, "page_end": 8, "warnings": [], "text": "x", "annotations": [],
        "status_label": LISTED_LABEL, "doc_id": "D"}


@pytest.mark.parametrize("over,expected", [
    ({}, "Source: NPC Circular 2022-04, section 10, pages 7-8 (issued 5 Dec 2022)"),
    ({"page_end": 7}, "Source: NPC Circular 2022-04, section 10, page 7 (issued 5 Dec 2022)"),
    ({"date_issued": ""}, "Source: NPC Circular 2022-04, section 10, pages 7-8"),
    ({"citation": "NPC Advisory 2017-01, Definition of Terms (m)"}, "Source: NPC Advisory 2017-01, Definition of Terms (m), pages 7-8 (issued 5 Dec 2022)"),
    ({"citation": "RA 10173, s.3(l)"}, "Source: RA 10173, section 3(l), pages 7-8 (issued 5 Dec 2022)"),
])
def test_source_line(over, expected):
    assert labels.source_text({**BASE, **over}) == expected


@pytest.mark.parametrize("over,expected", [
    ({"authority": "statute"}, "Law"), ({"authority": "rule"}, "Binding rule"), ({"authority": "guidance"}, "NPC guidance"),
    ({"authority": "draft"}, "Draft, not law"), ({"authority": "rule", "kind": "summary"}, "NPC summary"),
])
def test_type_wording(over, expected):
    assert labels.type_text({**BASE, **over}) == expected


def test_status_wording_changes_only_the_plain_listed_label():
    new = "NPC lists this document and notes no repeal. We have not checked it ourselves."
    rows = catalogue.load()
    for r in rows:
        shown = labels.status_display({"status": r["status"], "status_label": r["status_label"]})
        assert shown == (new if r["status_label"] == LISTED_LABEL else r["status_label"]), r["doc_id"]
        assert r["status"] == "draft" or "in force" not in shown
    assert sum(r["status_label"] == LISTED_LABEL for r in rows) == 22


def test_abbreviations_are_wrapped_for_display_only():
    text = "The PICs & DPO of NPC-IC; EPIC and pic stay."
    chunk = {**BASE, "text": text}
    page = web._hit_html(1, SimpleNamespace(chunk=chunk))
    assert chunk["text"] == text
    assert '<abbr title="Personal Information Controller">PICs</abbr> &amp; <abbr title="Data Protection Officer">DPO</abbr>' in page
    assert '<abbr title="National Privacy Commission">NPC</abbr>-<abbr title="Insurance Commission">IC</abbr>' in page
    assert "EPIC and pic stay." in page


def _hints():
    return {k[5:]: v["en"] for k, v in labels.load_labels().items() if k.startswith("abbr.")}


def test_every_hint_has_a_source_passage_that_gives_the_abbreviation_and_its_full_name():
    with open(ROOT / "data" / "processed" / "chunks.jsonl") as f:
        chunks = [json.loads(line) for line in f]
    text_by_citation = {}
    for c in chunks:
        flat = re.sub(r"\s+", " ", re.sub(r"([a-z])-\n([a-z])", r"\1\2", c["text"]))
        text_by_citation.setdefault(c["citation"], []).append(flat)
    with open(ROOT / "reports" / "abbreviation_sources.csv", newline="") as f:
        sources = list(csv.DictReader(f))
    assert {r["abbreviation"]: r["full_name"] for r in sources} == _hints()
    for r in sources:
        assert any(r["quote"] in text for text in text_by_citation[r["citation"]]), r["abbreviation"]
        assert r["full_name"].lower() in re.sub(r"\s+", " ", r["quote"]).lower() and r["abbreviation"] in r["quote"]
        assert "DRAFT" not in r["citation"], r["abbreviation"]


def test_requested_hints_exist_and_misleading_ones_stay_out():
    hints = _hints()
    assert {"DPO", "PIC", "PIP", "COP", "PIA", "DPA", "DSA"} <= set(hints)
    assert hints["DPA"] == "Data Privacy Act of 2012" and hints["DSA"] == "Data Sharing Agreement"
    # SEC mostly means "section" (SEC. 2). MCC has two wordings in the corpus. The others have no full name linked to them.
    assert not {"SEC", "MCC", "SPI", "PII", "ISO", "IEC", "NIST", "UPESO"} & set(hints)


def test_sec_heading_gets_no_hint():
    assert "<abbr" not in labels.abbreviate("SEC. 22. Heading")


def test_hints_stay_out_of_headings_and_source_lines():
    chunk = {**BASE, "text": "The DPA and a DSA", "warnings": ["NPC warning"], "citation": "NPC DPA DSA, s.10"}
    page = web._hit_html(1, SimpleNamespace(chunk=chunk))
    assert '<abbr title="Data Privacy Act of 2012">DPA</abbr> and a <abbr title="Data Sharing Agreement">DSA</abbr>' in page
    assert '<abbr title="National Privacy Commission">NPC</abbr> warning' in page
    assert "<h2>1. NPC DPA DSA, s.10</h2>" in page
    assert '<div class="meta">Source: NPC DPA DSA, section 10, pages 7-8 (issued 5 Dec 2022)</div>' in page
    for line in re.findall(r'<div class="meta">.*?</div>', page):
        assert "<abbr" not in line


def test_type_shows_marked_superseded_only_where_the_annotation_says_so():
    with open(ROOT / "data" / "processed" / "chunks.jsonl") as f:
        chunks = [json.loads(line) for line in f]
    marked = [c for c in chunks if c["kind"] != "footnote" and labels.type_text(c) == "Rule (marked superseded, see warning)"]
    assert sorted(c["citation"] for c in marked) == [f"IRR of RA 10173, s.20{s}" for s in ("", "(a)", "(b)", "(c)", "(d)")]
    warning = 'Superseded: the NPC annotation in this text reads "(The entire Section 20 is superseded by NPC Circular No. 2020-03)". See NPC Circular 2020-03.'
    assert all(warning in c["warnings"] for c in marked)
    amended = next(c for c in chunks if c["citation"] == "IRR of RA 10173, s.3(f)")
    assert labels.type_text(amended) == "Binding rule"
    other = next(c for c in chunks if c["citation"] == "IRR of RA 10173, s.22")
    assert labels.type_text(other) == "Binding rule"
    assert all(c["status"] == "amended" and c["block"] == "main" for c in marked)


@pytest.mark.parametrize("url,page,expected", [
    ("TBS", 3, None), ("", 3, None), ("http://privacy.gov.ph/a.pdf", 3, None), ("https://example.com/a.pdf", 3, None),
    ("https://privacy.gov.ph.example.com/a.pdf", 3, None),
    ("https://privacy.gov.ph/a.pdf", 3, "https://privacy.gov.ph/a.pdf#page=3"),
    ("https://www.privacy.gov.ph/A.PDF", 3, "https://www.privacy.gov.ph/A.PDF#page=3"),
    ("https://privacy.gov.ph/a/", 3, "https://privacy.gov.ph/a/"),
    ("https://privacy.gov.ph/a.pdf#x", 3, "https://privacy.gov.ph/a.pdf#x"),
])
def test_official_url_is_never_built_or_guessed(url, page, expected):
    assert catalogue.official_url(url, page) == expected


def test_link_opens_in_a_new_tab_only_when_the_catalogue_has_an_address(monkeypatch):
    hit = SimpleNamespace(chunk=BASE)
    monkeypatch.setattr(catalogue, "source_urls", lambda: {"D": "https://privacy.gov.ph/a.pdf"})
    page = web._hit_html(1, hit)
    assert ('<a href="https://privacy.gov.ph/a.pdf#page=7" target="_blank" rel="noopener noreferrer">'
            "Open the official document</a>") in page
    for address in ("TBS", "", "https://example.com/a.pdf"):
        monkeypatch.setattr(catalogue, "source_urls", lambda: {"D": address})
        assert "Open the official document" not in web._hit_html(1, hit)


def test_catalogue_rejects_an_address_that_is_not_official():
    rows = catalogue.load()
    rows[0]["source_url"] = "https://example.com/a.pdf"
    assert any("source_url" in e for e in catalogue.validate(rows))


FILLED_FIL_LABELS = {"banner.threshold_off"}  # approved by the project owner; add keys here as people fill them


def test_labels_file_has_the_columns_and_only_approved_filipino():
    # Filipino is written or approved by people. Every fil cell not listed above must stay empty.
    with open(ROOT / "data" / "i18n" / "labels.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == ["key", "en", "fil"] and all(r["key"] and r["en"] for r in rows)
    assert {r["key"] for r in rows if r["fil"]} == FILLED_FIL_LABELS


def test_filipino_falls_back_to_english_and_uses_a_label_when_there_is_one(monkeypatch):
    assert labels.label("page.search", "fil") == "Search"
    filled = {"page.search": {"key": "page.search", "en": "Search", "fil": "FIL-LABEL"}}
    monkeypatch.setattr(labels, "load_labels", lambda: filled)
    assert labels.label("page.search", "fil") == "FIL-LABEL" and labels.label("page.search", "en") == "Search"


def test_switch_keeps_the_query_and_never_touches_the_passage(base_url, monkeypatch):
    _, body, _ = _get(base_url + "/?q=a%26b&lang=fil")
    assert 'href="/?lang=en&amp;q=a%26b"' in body and 'href="/?lang=fil&amp;q=a%26b"' in body
    assert '<input type="hidden" name="lang" value="fil">' in body and 'lang="en"' in body
    assert "Passages are shown in the original English text." in body
    assert '<pre lang="en">Exact &lt;text&gt;' in body


def test_bad_language_value_falls_back_and_is_not_echoed(base_url):
    _, body, _ = _get(base_url + "/?q=term&lang=%22%3E%3Cb%3E")
    assert '<input type="hidden" name="lang" value="en">' in body and "<b>" not in body


def test_block_headings_match_the_fixed_layout():
    assert labels.label("block.pending") == BLOCK_HEADINGS[BLOCK_PENDING]
    assert labels.label("block.summary") == BLOCK_HEADINGS[BLOCK_SUMMARY]
