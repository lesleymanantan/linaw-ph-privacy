"""Chunk validation and search behaviour on the real corpus, plus synthetic splitting cases."""
import json
import socket
import subprocess
import sys

import pytest

from ph_privacy_guide.answer.warnings import annotation_warnings, status_warnings
from ph_privacy_guide.config import DRAFT_LABEL, PROCESSED, SUMMARY_LABEL
from ph_privacy_guide.index import bm25
from ph_privacy_guide.ingest import chunker
from ph_privacy_guide.retrieve.search import Searcher

needs_index = pytest.mark.skipif(not bm25.INDEX.exists(), reason="build the index first")


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


def test_annotation_warning_only_on_irr_and_only_for_listed_circular():
    cites = {"NPC_Circular_2022-04_Registration": "NPC Circular 2022-04"}
    notes = [{"number": 5, "text": "see [NPC Circular No.\n17-01] (2017)"}, {"number": 6, "text": "see [NPC Circular No. 20-03]"}]
    assert annotation_warnings("irr", notes, cites) == [
        "NPC annotation 5 cites NPC Circular 17-01, which is repealed. See NPC Circular 2022-04."]
    assert annotation_warnings("circular", notes, cites) == []


def test_chunk_validation_has_no_failures():
    chunks = _chunks()
    failed = [c for c in chunker.validate(chunks) if c["result"] == "FAIL"]
    assert failed == []


@needs_index
def test_no_excluded_or_non_searchable_chunks_in_results():
    s = Searcher()
    for query in ("whereas constitution", "approved commissioner", "footnote see national privacy commission"):
        for h in s.search(query, k=20).hits:
            assert h.chunk["kind"] in ("section", "part", "annex", "summary")


@needs_index
def test_draft_annex_behind_switch():
    s = Searcher()
    query = "privacy impact assessment template recommendatory"
    assert all(h.chunk["switch"] != "draft_annex" for h in s.search(query, k=50).hits)
    assert any(h.chunk["switch"] == "draft_annex" for h in s.search(query, k=50, include_draft_annex=True).hits)


@needs_index
def test_summary_ranks_below_sections():
    hits = Searcher().search("notification requirements breach", k=200).hits
    tiers = [h.chunk["rank_tier"] for h in hits]
    assert 1 in tiers and tiers == sorted(tiers)
    assert all(h.chunk["label"] == SUMMARY_LABEL for h in hits if h.chunk["rank_tier"] == 1)


@needs_index
def test_draft_hits_are_labelled():
    hits = Searcher().search("privacy impact assessment", k=200).hits
    drafts = [h for h in hits if h.chunk["collection"] == "drafts"]
    assert drafts and all(DRAFT_LABEL in h.chunk["citation"] for h in drafts)


@needs_index
def test_not_sure_when_nothing_matches():
    result = Searcher().search("xyzzy plugh")
    assert result.not_sure and result.hits == []


@needs_index
def test_full_query_runs_with_sockets_blocked():
    code = (
        "import socket\n"
        "from ph_privacy_guide.app.cli import main\n"
        "main(['data sharing agreement'])\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 9))\n"
        "except RuntimeError as e:\n"
        "    print('BLOCKED', type(e).__name__)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "Authority:" in out.stdout and "Not legal advice" in out.stdout
    assert "BLOCKED NetworkBlocked" in out.stdout
