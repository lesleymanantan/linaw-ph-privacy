"""The local page and the glossary file."""
import csv
import re
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from ph_privacy_guide.app import web
from ph_privacy_guide.config import CONTACT_URL, ROOT, WEB_HOST
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
    for needle in ("&lt;Cite&gt; s.1", "Authority: rule", "Status: not verified", "A &lt;warning&gt;", "Exact &lt;text&gt;\nsecond line", "NPC annotation 1"):
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


def test_page_says_when_not_sure_is_not_active(base_url):
    assert "is not active yet" in _get(base_url + "/?q=term")[1].replace("&quot;", '"')
    assert "is not active yet" not in _get(base_url + "/?q=calibrated")[1].replace("&quot;", '"')
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


def test_glossary_has_english_terms_and_no_filipino():
    path = ROOT / "data" / "glossary" / "en_fil_terms.csv"
    if not path.exists():
        pytest.skip("run scripts/build_glossary.py first")
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and all(r["en_term"] and r["en_source_chunk_id"] for r in rows)
    for r in rows:
        assert r["fil_term"] == r["fil_variants"] == r["fil_source"] == r["fil_reviewer"] == ""
    assert all("DRAFT" not in r["en_source_citation"] for r in rows)
