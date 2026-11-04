"""Chunk validation and search behaviour on the real corpus, plus synthetic splitting cases."""
import json
import subprocess
import sys

import pytest

from ph_privacy_guide.answer.warnings import annotation_warnings, status_warnings
from ph_privacy_guide.config import DRAFT_LABEL, PROCESSED, RANK_TIER_DRAFT, RRF_K, SUMMARY_LABEL
from ph_privacy_guide.index import bm25
from ph_privacy_guide.index.embed import VECTORS
from ph_privacy_guide.ingest import chunker
from ph_privacy_guide.answer.format import format_result
from ph_privacy_guide.retrieve.search import Searcher, fuse

needs_index = pytest.mark.skipif(not bm25.INDEX.exists() or not VECTORS.exists(), reason="build the indexes first")


@pytest.fixture(scope="module")
def searcher():
    return Searcher()


def _chunks():
    return [json.loads(line) for line in open(PROCESSED / "chunks.jsonl")]


def test_find_items_needs_a_sequential_run():
    assert [v for _, v in chunker.find_items(["(a) one", "text", "(b) two", "(d) skipped"])] == ["a", "b"]
    assert chunker.find_items(["(a) only one", "text"]) == []


def test_forced_split_gives_one_piece_per_term():
    pieces = chunker.split_lines(["Lead in text:", "(a) first term", "(b) second term"], force=True)
    assert [s for s, _ in pieces] == ["", "(a)", "(b)"]


def test_long_text_without_items_is_packed_and_nothing_lost():
    lines = [("word " * 90).strip() + "." for _ in range(8)]
    pieces = chunker.split_lines(lines, limit=200)
    assert len(pieces) > 1
    assert [l for _, ls in pieces for l in ls] == lines
    assert all(chunker._join_words(ls) <= 200 for _, ls in pieces)


def test_repealed_status_warning_names_the_replacement():
    rec = {"status": "repealed", "replaced_by": "X", "supplemented_by": "", "label": ""}
    assert status_warnings(rec, {"X": "NPC Circular X"}) == ["REPEALED: replaced by NPC Circular X."]


def test_annotation_warnings_only_on_irr_and_only_for_listed_circulars():
    cites = {"NPC_Circular_2022-04_Registration": "NPC Circular 2022-04", "NPC_Circular_2023-06_Security": "NPC Circular 2023-06"}
    notes = [{"number": 5, "text": "see [NPC Circular No.\n17-01] (2017)"}, {"number": 6, "text": "see [NPC Circular No. 20-03]"},
             {"number": 17, "text": "see [NPC Circular No. 16-01] (2016)"}]
    assert annotation_warnings("irr", notes, cites) == [
        "NPC annotation 5 cites NPC Circular 17-01, which is repealed. See NPC Circular 2022-04 (s.40 supersedes 17-01).",
        "NPC annotation 17 cites NPC Circular 16-01, which is repealed. See NPC Circular 2023-06 (s.39 repeals 16-01)."]
    assert annotation_warnings("circular", notes, cites) == []


def test_real_irr_notes_citing_16_01_warn_on_s30_and_s49():
    warned = [c for c in _chunks() if c["doc_id"] == "IRR_RA10173" and any("16-01" in w and "2023-06" in w for w in c["warnings"])]
    assert {c["section"] for c in warned} == {"30", "49"}


def test_every_draft_chunk_is_in_the_draft_tier():
    for c in _chunks():
        if c["kind"] != "footnote":
            assert (c["rank_tier"] == RANK_TIER_DRAFT) == (c["status"] == "draft"), c["chunk_id"]


def test_fusion_uses_reciprocal_ranks_with_equal_weights():
    scores = fuse([([1, 2], 1.0), ([2, 3], 1.0)], k=RRF_K)
    assert scores[2] == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert scores[1] == pytest.approx(1 / (RRF_K + 1))
    assert scores[3] == pytest.approx(1 / (RRF_K + 2))


def test_chunk_validation_has_no_failures():
    chunks = _chunks()
    failed = [c for c in chunker.validate(chunks) if c["result"] == "FAIL"]
    assert failed == []


@needs_index
def test_only_searchable_kinds_in_results(searcher):
    for query in ("whereas constitution", "approved commissioner", "see national privacy commission"):
        for h in searcher.search(query, k=20).hits:
            assert h.chunk["kind"] in ("section", "part", "annex", "summary")


@needs_index
def test_draft_annex_behind_switch(searcher):
    query = "privacy impact assessment template recommendatory"
    assert all(h.chunk["switch"] != "draft_annex" for h in searcher.search(query, k=966).hits)
    assert any(h.chunk["switch"] == "draft_annex" for h in searcher.search(query, k=966, include_draft_annex=True).hits)


@needs_index
def test_shown_passages_are_ordered_by_tier(searcher):
    hits = searcher.search("privacy impact assessment notification breach", k=966).hits
    tiers = [h.chunk["rank_tier"] for h in hits]
    assert tiers == sorted(tiers)
    assert set(tiers) == {0, 1, 2}
    assert all(h.chunk["label"] == SUMMARY_LABEL for h in hits if h.chunk["rank_tier"] == 1)
    assert all(DRAFT_LABEL in h.chunk["citation"] for h in hits if h.chunk["rank_tier"] == 2)


@needs_index
def test_not_sure_shows_no_passage(searcher):
    result = searcher.search("xyzzy plugh")
    assert result.not_sure
    text = format_result("xyzzy plugh", result)
    assert "Not sure" in text and "Authority:" not in text
    assert "https://privacy.gov.ph/contactus/" in text


@needs_index
def test_not_sure_threshold_comes_from_config(searcher, monkeypatch):
    from ph_privacy_guide.retrieve import search as module

    terms = "data sharing xyzzy plugh quux"  # 2 of 5 terms can match
    monkeypatch.setattr(module, "NOT_SURE_MIN_TERM_COVERAGE", 0.5)
    assert searcher.search(terms).not_sure
    monkeypatch.setattr(module, "NOT_SURE_MIN_TERM_COVERAGE", 0.3)
    assert not searcher.search(terms).not_sure


@needs_index
def test_full_hybrid_query_runs_with_sockets_blocked():
    code = (
        "import socket, sys\n"
        "from ph_privacy_guide.app.cli import main\n"
        "main(['data sharing agreement'])\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 9))\n"
        "except RuntimeError as e:\n"
        "    print('BLOCKED', type(e).__name__)\n"
        "print('HUB_LOADED', 'huggingface_hub' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "Authority:" in out.stdout and "Not legal advice" in out.stdout
    assert "BLOCKED NetworkBlocked" in out.stdout
    assert "HUB_LOADED False" in out.stdout
