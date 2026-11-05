"""Sectioner tests: synthetic cases, plus checks on the real corpus when it has been processed."""
import json

import pytest

from ph_privacy_guide import catalogue
from ph_privacy_guide.config import ANNOTATION_LABEL, DRAFT_LABEL, PROCESSED, SUMMARY_LABEL
from ph_privacy_guide.ingest import sectioner as S

ROW = {"doc_id": "X", "short_cite": "X", "type": "circular", "status": "unverified", "authority": "rule",
       "replaced_by": "", "clarified_by": "", "date_issued": "", "version": "", "collection": "privacy-law",
       "title": "X", "parent_doc_id": ""}


def _doc(body, **over):
    return S.section_document({**ROW, **over}, [(1, body)])


def test_heading_without_dot_after_sec_is_found():
    assert _doc("SEC. 1. Title. – A.\nSEC 2. Next. – B.\nSEC. 3. Last. – C.").numbers == [1, 2, 3]


def test_cross_references_are_not_headings():
    res = _doc("SECTION 1. Scope. A\nSection 30 of the DPA.\nSECTION 2. Next. B\nSection 6: provided, that")
    assert res.numbers == [1, 2]
    assert res.possible_missed == []
    assert res.xrefs_dismissed == 2


def test_gap_is_reported():
    assert _doc("SECTION 1. A. x\nSECTION 3. B. y").gaps == [2]


def test_duplicate_is_reported():
    res = _doc("SECTION 1. A. x\nSECTION 2. B. y\nSECTION 2. C. z\nSECTION 3. D. w")
    assert res.numbers == [1, 2, 3]
    assert len(res.duplicates) == 1


def test_stray_high_number_does_not_derail_sequence():
    res = _doc("SECTION 1. A. x\nSection 40. Reference. y\nSECTION 2. B. z\nSECTION 3. C. w")
    assert res.numbers == [1, 2, 3]
    assert len(res.out_of_sequence) == 1


def test_heading_with_bad_punctuation_is_flagged_as_possible_miss():
    res = _doc("SECTION 1. A. x\nSECTION 2 Missing Stop. y\nSECTION 3. B. z")
    assert res.gaps == [2]
    assert len(res.possible_missed) == 1


def test_margin_numbers_removed_but_table_and_footnote_numbers_kept():
    # Margin numbers must establish a run first: 1-3 on page 1, then well past the table's values.
    margin = "\n".join(f"{i} body line {i}" for i in range(1, 9))
    margin += "\n" + "\n".join(f"{i} more text {i}" for i in range(10, 41, 10))
    pages = [(1, margin + "\n1 Footnote text\n50 after note\n5 10 15 20 25\n51 last line")]
    text = [l.text for l in S.clean_pages(pages).lines]
    assert text[:2] == ["body line 1", "body line 2"]
    assert text[-4:] == ["1 Footnote text", "after note", "5 10 15 20 25", "last line"]


# Real corpus -----------------------------------------------------------------------------------

def _records(doc_id):
    path = PROCESSED / "sections" / f"{doc_id}.jsonl"
    if not path.exists():
        pytest.skip("run ph_privacy_guide.ingest.sectioner first")
    return [json.loads(line) for line in path.open()]


def _sections(doc_id):
    return [r for r in _records(doc_id) if r["kind"] == "section"]


def test_ra10173_numbers_run_unbroken_to_45():
    # The text itself has 45 sections (s.44 Repealing, s.45 Effectivity); the stated 44 is reported as FAIL.
    assert [int(r["section"]) for r in _sections("RA10173_DPA_2012")] == list(range(1, 46))


def test_all_sectioned_docs_are_contiguous_with_effectivity_clause():
    for row in catalogue.load():
        if row["in_corpus"] == "yes" and row["type"] in S.LAW_TYPES:
            secs = _sections(row["doc_id"])
            assert [int(r["section"]) for r in secs] == list(range(1, len(secs) + 1)), row["doc_id"]
            assert S.EFFECTIVITY_TITLE_RE.search(secs[-1]["title"]), row["doc_id"]
            assert S.EFFECTIVITY_TEXT_RE.search(secs[-1]["text"]), row["doc_id"]


def test_known_repealing_clauses_land_in_the_right_sections():
    reg = {r["section"]: r for r in _sections("NPC_Circular_2022-04_Registration")}
    assert "supersedes in its entirety" in reg["40"]["text"]
    sec = {r["section"]: r for r in _sections("NPC_Circular_2023-06_Security")}
    assert "expressly repeals" in sec["39"]["text"]


def test_annex1_is_one_block():
    recs = _records("NPC_Circular_2022-04_Annex1")
    assert [r["kind"] for r in recs] == ["annex"]
    assert (recs[0]["page_start"], recs[0]["page_end"]) == (1, 2)


def test_every_draft_record_is_labelled_and_nothing_else_is():
    for row in catalogue.load():
        if row["in_corpus"] == "yes" and row["type"] in S.SECTIONED_TYPES | S.WHOLE_DOC_TYPES:
            for r in _records(row["doc_id"]):
                if row["collection"] == "drafts":
                    assert DRAFT_LABEL in (r["label"], r.get("draft_label"))
                    assert DRAFT_LABEL in r["citation"]
                    assert r["status"] == "draft" and r["authority"] == "draft"
                else:
                    assert DRAFT_LABEL not in r["label"] and DRAFT_LABEL not in r["citation"]


def test_footnotes_are_out_of_section_text_and_linked():
    recs = _records("IRR_RA10173")
    notes = [r for r in recs if r["kind"] == "footnote"]
    assert [int(r["section"]) for r in notes] == list(range(1, 27))
    assert all(r["label"] == ANNOTATION_LABEL and r["parent_section"] for r in notes)
    body = "\n".join(r["text"] for r in recs if r["kind"] == "section")
    assert "Original provision:" not in body
    assert "[NPC Circular No. 17-01]" not in body


def test_summary_and_draft_annex_are_separate_records():
    summary = [r for r in _records("NPC_Circular_16-03_Breach_Management") if r["kind"] == "summary"]
    assert len(summary) == 1 and summary[0]["label"] == SUMMARY_LABEL
    annex = [r for r in _records("DRAFT_Updated_PIA_Guidelines_Circular") if r["kind"] == "annex"]
    assert len(annex) == 1 and annex[0]["label"] == DRAFT_LABEL


def test_every_document_is_sectioned_with_no_lost_text():
    results = S.run()
    assert len(results) == 28
    assert [r.doc_id for r in results if S._lost(r)] == []


def test_draft_keeps_risk_matrix_numbers():
    text = "\n".join(r["text"] for r in _records("DRAFT_Updated_PIA_Guidelines_Circular"))
    assert "5 10 15 20 25" in text
