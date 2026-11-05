"""Chunk validation and search behaviour on the real corpus, plus synthetic splitting cases."""
import csv
import json
import subprocess
import sys

import pytest

from ph_privacy_guide.answer.warnings import annotation_warnings, status_warnings, text_annotation_warnings
from ph_privacy_guide.config import (BLOCK_MAIN, BLOCK_PENDING, BLOCK_SUMMARY, DRAFT_LABEL, KEYWORD_ONLY_NOTE, MAIN_RESULTS,
                                     PROCESSED, ROOT, RRF_K, SIDE_BLOCK_MAX, SUMMARY_LABEL)
from ph_privacy_guide.index import bm25
from ph_privacy_guide.index.embed import VECTORS, VECTORS_META
from ph_privacy_guide.ingest import chunker
from ph_privacy_guide.answer.format import format_result
from ph_privacy_guide.retrieve.confidence import combine, compute_features, is_not_sure
from ph_privacy_guide.retrieve.search import Searcher, fuse, select_side

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
    rec = {"status": "repealed", "replaced_by": "X", "clarified_by": "", "label": ""}
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


def test_irr_warnings_quote_the_annotation_on_the_chunks_it_covers():
    irr = [c for c in _chunks() if c["doc_id"] == "IRR_RA10173" and c["kind"] == "section"]
    amended = '"(as amended by NPC Circular No. 2020-03)"'
    superseded = '"(The entire Section 20 is superseded by NPC Circular No. 2020-03)"'
    assert {c["citation"] for c in irr if any(amended in w for w in c["warnings"])} == {"IRR of RA 10173, s.3(f)"}
    covered = {c["chunk_id"] for c in irr if any(superseded in w for w in c["warnings"])}
    assert covered == {c["chunk_id"] for c in irr if c["section"] == "20"} and len(covered) == 5
    assert all("See NPC Circular 2020-03." in w for c in irr for w in c["warnings"] if amended in w or superseded in w)


def test_annotation_warning_stops_the_build_if_the_quote_is_not_in_the_text():
    chunk = {"kind": "section", "doc_id": "IRR_RA10173", "section": "20", "subsection": "(a)"}
    with pytest.raises(ValueError, match="annotation not found"):
        text_annotation_warnings(chunk, "Section 20 without the note.", {"NPC_Circular_2020-03_Data_Sharing_Agreements": "X"})


def test_document_warnings_on_advisory_2017_03_and_annex_1():
    chunks = _chunks()
    advisory = [c for c in chunks if c["doc_id"] == "NPC_Advisory_2017-03_PIA"]
    text = "A draft circular (not in force) would supersede this advisory if adopted. Check the NPC site for the current position."
    assert advisory and all(text in c["warnings"] and c["status_label"] == "not verified" for c in advisory)
    annex = next(c for c in chunks if c["doc_id"] == "NPC_Circular_2022-04_Annex1")
    assert "Annex of NPC Circular 2022-04. Its status follows the circular." in annex["warnings"]


def test_pending_pia_warning_is_on_circular_2023_06_s4_s5_s7_only():
    text = ("A draft circular (not in force) would change when a privacy impact assessment is required. "
            "Check the NPC site for the current position.")
    warned = [c for c in _chunks() if text in c["warnings"]]
    assert sorted(c["citation"] for c in warned) == [f"NPC Circular 2023-06, s.{n}" for n in (4, 5, 7)]
    assert "D. Conduct a Privacy Impact Assessment" in warned[0]["text"]
    assert all(c["status"] == "listed_no_repeal" and c["block"] == BLOCK_MAIN for c in warned)


HEADER = ("NPC Advisory No. 2026-02 – Clarification on the\nSubmission of Personal Data Breach Notification\n"
          "through Data Breach Notification Management\nSystem\nPage 2 of 3\n")
ADVISORY = "NPC_Advisory_2026-02_DBNMS_Clarification"


def test_cleaning_rule_removes_only_the_running_header():
    text, removed = chunker.clean_section_text(ADVISORY, "section", "2", "advising the\n" + HEADER + "stakeholders of")
    assert text == "advising the\nstakeholders of" and [r["removed_text"] for r in removed] == [HEADER]
    for other in (("OTHER_DOC", "section", "2"), (ADVISORY, "section", "1"), (ADVISORY, "footnote", "2")):
        assert chunker.clean_section_text(*other, HEADER) == (HEADER, [])
    for near_miss in (HEADER.replace("Page 2 of 3\n", ""), HEADER.replace("2026-02", "2026-03"), "See " + HEADER):
        assert chunker.clean_section_text(ADVISORY, "section", "2", near_miss) == (near_miss, [])


def test_header_is_gone_from_chunks_and_kept_in_section_records():
    chunks = [c for c in _chunks() if c["doc_id"] == ADVISORY]
    target = next(c for c in chunks if c["citation"].endswith("s.2(B)"))
    assert "advising the\nstakeholders of the fact" in target["text"]
    assert "Page 2 of 3" not in target["text"] and "Page 2 of 3" not in target["index_text"]
    log = chunker.cleaning_log()
    assert len(log) == 1 and log[0]["removed_text"] == HEADER and log[0]["rule"] == "advisory-2026-02-running-header"
    with open(PROCESSED / "sections" / f"{ADVISORY}.jsonl") as f:
        assert any("Page 2 of 3" in json.loads(line)["text"] for line in f)


def test_chunks_carry_the_catalogue_label_and_the_page_shows_it():
    from ph_privacy_guide.answer.format import format_hit
    from types import SimpleNamespace

    chunks = _chunks()
    sample = next(c for c in chunks if c["doc_id"] == "NPC_Advisory_2026-01_Data_Scraping" and c["kind"] == "section")
    text = format_hit(1, SimpleNamespace(chunk=sample))
    assert "Status: NPC lists this document and notes no repeal. We have not checked it ourselves." in text
    assert "Type: NPC guidance" in text and "Authority:" not in text and "Issued:" not in text
    assert sample["status_label"] == "Listed by NPC, no repeal noted; not independently verified"
    breach = next(c for c in chunks if c["doc_id"] == "NPC_Circular_16-03_Breach_Management" and c["kind"] == "section")
    assert "Status: Listed by NPC, no repeal noted. Advisory 2026-02 (2026-05) gives clarifications" in format_hit(1, SimpleNamespace(chunk=breach))
    ra = next(c for c in chunks if c["doc_id"] == "RA10173_DPA_2012" and c["kind"] == "section")
    assert "Status: Downloaded from NPC's DPA and IRR page" in format_hit(1, SimpleNamespace(chunk=ra))


def test_every_chunk_is_in_the_right_block():
    for c in _chunks():
        if c["kind"] == "footnote":
            continue
        expected = BLOCK_PENDING if c["status"] == "draft" else BLOCK_SUMMARY if c["kind"] == "summary" else BLOCK_MAIN
        assert c["block"] == expected, c["chunk_id"]


def test_fusion_uses_reciprocal_ranks_with_equal_weights():
    scores = fuse([([1, 2], 1.0), ([2, 3], 1.0)], k=RRF_K)
    assert scores[2] == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert scores[1] == pytest.approx(1 / (RRF_K + 1))
    assert scores[3] == pytest.approx(1 / (RRF_K + 2))


def test_chunk_validation_has_no_failures():
    chunks = _chunks()
    failed = [c for c in chunker.validate(chunks) if c["result"] == "FAIL"]
    assert failed == []


def test_token_split_fits_budget_keeps_all_lines_and_overlaps_one_sentence():
    count = lambda text: len(text.split())
    lines = [f"First sentence {i} here. Second sentence {i} here." for i in range(10)]
    pieces = chunker.split_by_tokens(lines, 30, count)
    assert len(pieces) > 1
    assert all(count("\n".join(ls)) <= 30 for ls, _ in pieces)
    assert pieces[0][1] == 0 and all(ov > 0 for _, ov in pieces[1:])
    # Without the overlap, the pieces rebuild the original exactly.
    assert [l for ls, ov in pieces for l in ls[ov:]] == lines
    # The overlap is the previous piece's last sentence.
    assert pieces[1][0][0] == pieces[0][0][-1].split(". ")[-1]


def test_short_text_is_not_token_split():
    assert chunker.split_by_tokens(["a b c"], 30, lambda t: len(t.split())) == [(["a b c"], 0)]


def test_a_single_overlong_line_is_broken_at_words():
    line = " ".join(f"w{i}" for i in range(100))
    pieces = chunker.split_by_tokens([line], 30, lambda t: len(t.split()))
    assert all(len(" ".join(ls).split()) <= 30 for ls, _ in pieces)


def test_only_annex_1_goes_past_the_model_limit():
    if not VECTORS_META.exists():
        pytest.skip("build the indexes first")
    assert json.loads(VECTORS_META.read_text())["truncated_chunks"] == ["NPC_Circular_2022-04_Annex1:annex:annex"]
    marked = [c["chunk_id"] for c in _chunks() if KEYWORD_ONLY_NOTE in c["notes"]]
    assert marked == ["NPC_Circular_2022-04_Annex1:annex:annex"]


def test_the_four_long_chunks_were_split_with_overlap():
    by_id = {c["chunk_id"]: c for c in _chunks()}
    for stem in ("NPC_Advisory_2021-01_Data_Subject_Rights:annex:annex:part-1", "NPC_Advisory_2021-01_Data_Subject_Rights:annex:annex:part-2",
                 "NPC_Advisory_2024-01_Cross_Border_Clauses:section:3", "DRAFT_Updated_PIA_Guidelines_Circular:section:4:a"):
        assert stem not in by_id, stem
        parts = [c for cid, c in by_id.items() if cid.startswith((stem + "-", stem + ":part-")) and c["kind"] != "footnote"]
        assert len(parts) >= 2, stem
        assert any(c["overlap_chars"] for c in parts), stem


def test_only_those_four_were_split_by_tokens():
    overlapped = {c["doc_id"] + " s." + c["section"] for c in _chunks() if c["overlap_chars"]}
    assert overlapped == {"NPC_Advisory_2021-01_Data_Subject_Rights s.annex", "NPC_Advisory_2024-01_Cross_Border_Clauses s.3",
                          "DRAFT_Updated_PIA_Guidelines_Circular s.4"}


def test_gold_paths():
    assert chunker.gold_path("section", "3", "(l)") == "s.3(l)"
    assert chunker.gold_path("section", "7", ", part 2") == "s.7"
    assert chunker.gold_path("section", "4", "(a), part 1") == "s.4(a)"
    assert chunker.gold_path("part", "scope", "(m)") == "part:scope(m)"
    assert chunker.gold_path("annex", "annex", ", part 1.2") == "annex"
    assert chunker.gold_path("summary", "summary", "") == "summary"
    assert chunker.gold_path("preamble", "preamble", "") == ""


def test_gold_labels_file_lists_sections_and_subsections():
    with open(ROOT / "eval" / "gold_labels.csv", newline="") as f:
        labels = {r["gold_label"]: r for r in csv.DictReader(f)}
    for label in ("NPC_Circular_2022-04 s.7", "RA10173 s.3", "RA10173 s.3(l)", "IRR_RA10173 s.47", "NPC_Circular_2022-04_Annex1 annex",
                  "NPC_Circular_16-03 summary", "DRAFT_PIA_Circular annex", "NPC_Advisory_2017-01 part:scope"):
        assert label in labels, label
    assert labels["RA10173 s.3(l)"]["chunks"] == "1"
    assert int(labels["RA10173 s.3"]["chunks"]) > 10
    assert labels["DRAFT_PIA_Circular annex"]["searchable_by_default"] == "no"


def test_select_side_needs_the_bar_and_takes_one_per_block():
    blocks = {1: BLOCK_MAIN, 2: BLOCK_PENDING, 3: BLOCK_PENDING, 4: BLOCK_SUMMARY, 5: BLOCK_MAIN}
    score = {1: 0.9, 2: 0.7, 3: 0.6, 4: 0.2, 5: 0.5}
    assert select_side([1, 2, 3, 5, 4], score, blocks.get, 0.5) == [(BLOCK_PENDING, 2)]
    assert select_side([1, 2, 3, 5, 4], score, blocks.get, 0.1) == [(BLOCK_PENDING, 2), (BLOCK_SUMMARY, 4)]
    assert select_side([1, 2, 3, 5, 4], score, blocks.get, 0.95) == []
    assert select_side([1, 2, 3, 5, 4], score, blocks.get, None) == []
    assert SIDE_BLOCK_MAX == 1 and MAIN_RESULTS == 3


def test_confidence_features():
    best = 2 / (RRF_K + 1)
    f = compute_features([best, best / 2], [7, 8], [7, 9], 0.8, 0.5)
    assert f["top_fused"] == pytest.approx(1.0) and f["margin"] == pytest.approx(0.5)
    assert f["agreement"] == 1.0 and f["top_cosine"] == 0.8 and f["term_coverage"] == 0.5
    assert compute_features([best], [1, 2, 3], [4, 2, 3], 0.5, 0)["agreement"] == pytest.approx(0.4)
    assert compute_features([], [], [], -0.2, 0)["top_cosine"] == 0.0


def test_term_overlap_is_one_feature_and_cannot_gate_alone():
    features = {"top_fused": 1.0, "margin": 1.0, "agreement": 1.0, "top_cosine": 1.0, "term_coverage": 0.0}
    assert combine(features) == pytest.approx(0.8)
    assert not is_not_sure(combine(features), 0.5)


def test_threshold_none_withholds_nothing():
    assert not is_not_sure(0.0, None)
    assert is_not_sure(0.4, 0.5) and not is_not_sure(0.5, 0.5)


def test_threshold_is_not_set_before_the_dev_set_exists():
    from ph_privacy_guide import config
    from ph_privacy_guide.evaluate.questions import load_split

    if not load_split("dev"):
        assert config.NOT_SURE_CONFIDENCE_THRESHOLD is None


@needs_index
def test_only_searchable_kinds_in_results(searcher):
    for query in ("whereas constitution", "approved commissioner", "see national privacy commission"):
        result = searcher.search(query, k=20)
        for h in result.hits + [h for _, h in result.side]:
            assert h.chunk["kind"] in ("section", "part", "annex", "summary")


@needs_index
def test_draft_annex_behind_switch(searcher):
    annex = [c for c in searcher.index_chunks if c["switch"] == "draft_annex"]
    assert annex and not any(searcher._allowed(c, False) for c in annex) and all(searcher._allowed(c, True) for c in annex)
    result = searcher.search("privacy impact assessment template recommendatory")
    assert all(h.chunk["switch"] != "draft_annex" for _, h in result.side)


@needs_index
def test_main_block_never_holds_a_draft_or_the_summary(searcher):
    for query in ("privacy impact assessment threshold analysis", "summary notification requirements breach"):
        for h in searcher.search(query, k=966).hits:
            assert h.chunk["block"] == BLOCK_MAIN and h.chunk["status"] != "draft" and h.chunk["kind"] != "summary"


@needs_index
def test_main_block_shows_three_by_default(searcher):
    assert len(searcher.search("data sharing agreement").hits) == MAIN_RESULTS


@needs_index
def test_side_blocks_are_labelled_capped_and_clear_the_bar(searcher):
    result = searcher.search("threshold analysis privacy impact assessment")
    pending = [h for block, h in result.side if block == BLOCK_PENDING]
    assert len(pending) == 1 and DRAFT_LABEL in pending[0].chunk["citation"]
    assert pending[0].score >= result.hits[-1].score
    text = format_result("x", result)
    assert "=== Pending change: draft, not law ===" in text
    assert text.index("=== Pending change") > text.index("[3]")


@needs_index
def test_the_bar_does_not_move_with_k(searcher):
    query = "threshold analysis privacy impact assessment"
    assert [h.chunk["chunk_id"] for _, h in searcher.search(query, k=5).side] == [h.chunk["chunk_id"] for _, h in searcher.search(query).side]


@needs_index
def test_without_a_threshold_passages_show_with_a_plain_note(searcher):
    result = searcher.search("xyzzy plugh")
    assert not result.not_sure and not result.calibrated and result.hits
    assert 'The "not sure" check is switched off for now, so these results may not answer your question.' in format_result("xyzzy plugh", result)


@needs_index
def test_filipino_terms_are_not_gated_on_english_overlap(searcher):
    result = searcher.search("pahintulot karapatan")
    assert result.features["term_coverage"] == 0.0
    assert not result.not_sure and result.hits


@needs_index
def test_empty_search_is_not_sure(searcher):
    assert searcher.search("   ").not_sure


@needs_index
def test_threshold_comes_from_config_and_hides_passages(searcher, monkeypatch):
    from ph_privacy_guide.retrieve import search as module

    monkeypatch.setattr(module, "NOT_SURE_CONFIDENCE_THRESHOLD", 1.01)
    result = searcher.search("data sharing agreement")
    assert result.not_sure and result.calibrated
    text = format_result("data sharing agreement", result)
    assert "Not sure" in text and "Type:" not in text and "https://privacy.gov.ph/contactus/" in text
    monkeypatch.setattr(module, "NOT_SURE_CONFIDENCE_THRESHOLD", 0.0)
    result = searcher.search("data sharing agreement")
    assert not result.not_sure and "switched off" not in format_result("x", result)


@needs_index
def test_confidence_is_reported_with_every_feature(searcher):
    result = searcher.search("data sharing agreement")
    assert set(result.features) == {"top_fused", "margin", "agreement", "top_cosine", "term_coverage"}
    assert 0.0 <= result.confidence <= 1.0
    assert all(0.0 <= v <= 1.0 for v in result.features.values())


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
    assert "Type:" in out.stdout and "Not legal advice" in out.stdout
    assert "BLOCKED NetworkBlocked" in out.stdout
    assert "HUB_LOADED False" in out.stdout
