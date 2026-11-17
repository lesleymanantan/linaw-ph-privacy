"""Glossary import, rebuild and keyword expansion. Placeholder tokens only: no Filipino words here."""
import csv

import pytest

from ph_privacy_guide import config, glossary
from ph_privacy_guide.evaluate import metrics
from ph_privacy_guide.index import bm25
from ph_privacy_guide.index.embed import VECTORS
from ph_privacy_guide.retrieve.search import Searcher

needs_index = pytest.mark.skipif(not bm25.INDEX.exists() or not VECTORS.exists(), reason="build the indexes first")

PLACEHOLDER = "zzqplaceholder"
BASE = {"en_source_citation": "NPC Circular 2023-06, s.3(A)", "en_source_chunk_id": "x:section:3:a", "n_sources": "1"}


def _row(en_term, **fil):
    return {"en_term": en_term, **BASE, **{c: fil.get(c, "") for c in glossary.FIL_COLUMNS}}


def _write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    return path


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "glossary.csv"
    glossary.write_rows([_row("Acceptable Use Policy"), _row("Access Controls")], path)
    return path


def _import(tmp_path, store, rows, columns=None):
    source = _write_csv(tmp_path / "input.csv", columns or glossary.IMPORT_COLUMNS, rows)
    return glossary.import_csv(source, store)


def test_import_matches_ignoring_case_and_ignores_ref_columns(tmp_path, store):
    columns = ["ref_note", *glossary.IMPORT_COLUMNS, "ref_other"]
    report = _import(tmp_path, store, [["anything", "acceptable USE policy", "zzqone", "zzqtwo;zzqthree", "A source", "A reviewer", "more"]], columns)
    assert report.written and report.errors == [] and report.imported == ["Acceptable Use Policy"]
    row = glossary.read_rows(store)[0]
    assert row == _row("Acceptable Use Policy", fil_term="zzqone", fil_variants="zzqtwo;zzqthree", fil_source="A source", fil_reviewer="A reviewer")


def test_import_skips_rows_with_no_fil_term_and_lists_unmatched_rows(tmp_path, store):
    report = _import(tmp_path, store, [["Access Controls", "", "zzqtwo", "A source", "A reviewer"],
                                       ["Not In The List", "zzqone", "", "A source", "A reviewer"],
                                       ["Acceptable Use Policy", "zzqone", "", "A source", ""]])
    assert report.written and report.imported == ["Acceptable Use Policy"]
    assert len(report.skipped) == 1 and "Access Controls" in report.skipped[0]
    assert len(report.unmatched) == 1 and "Not In The List" in report.unmatched[0]
    rows = {r["en_term"]: r for r in glossary.read_rows(store)}
    assert set(rows) == {"Acceptable Use Policy", "Access Controls"} and rows["Access Controls"]["fil_variants"] == ""


@pytest.mark.parametrize("bad,problem", [
    (["Access Controls", "zzqone", "", "", "A reviewer"], "no fil_source"),
    (["Acceptable Use Policy", "zzqone", "", "A source", "A reviewer"], "more than once"),
    (["", "zzqone", "", "A source", "A reviewer"], "no en_term"),
    (["Access Controls", "zzqone;zzqtwo", "", "A source", "A reviewer"], "fil_variants"),
    (["Not In The List", "zzqone", "", "", "A reviewer"], "no fil_source"),
])
def test_one_invalid_row_means_nothing_is_written(tmp_path, store, bad, problem):
    before = store.read_bytes()
    report = _import(tmp_path, store, [["Acceptable Use Policy", "zzqone", "", "A source", "A reviewer"], bad])
    assert not report.written and any(problem in e for e in report.errors)
    assert store.read_bytes() == before


@pytest.mark.parametrize("columns", [
    ["en_term", "fil_term", "fil_variants", "fil_source"],
    [*glossary.IMPORT_COLUMNS, "extra"],
])
def test_wrong_columns_mean_nothing_is_written(tmp_path, store, columns):
    before = store.read_bytes()
    report = _import(tmp_path, store, [["Access Controls", "zzqone", "", "A source", "A reviewer", "x"][:len(columns)]], columns)
    assert not report.written and report.errors and store.read_bytes() == before


def test_rebuild_keeps_filipino_values_matching_en_term():
    filled = dict(fil_term="zzqone", fil_variants="zzqtwo", fil_source="A source", fil_reviewer="A reviewer")
    merged, errors = glossary.keep_filipino([_row("ACCESS controls"), _row("New Term")], [_row("Access Controls", **filled)])
    assert errors == []
    assert merged == [_row("ACCESS controls", **filled), _row("New Term")]


def test_rebuild_stops_rather_than_lose_filipino_values():
    _, errors = glossary.keep_filipino([_row("New Term")], [_row("Access Controls", fil_term="zzqone", fil_source="A source"), _row("Unfilled")])
    assert len(errors) == 1 and "Access Controls" in errors[0]


def _entries(tmp_path, **fil):
    path = tmp_path / "entries.csv"
    glossary.write_rows([_row("Acceptable Use Policy", **fil)], path)
    return glossary.load_expansions(path)


def test_only_reviewed_rows_expand(tmp_path):
    assert _entries(tmp_path, fil_term=PLACEHOLDER, fil_source="A source") == []
    assert glossary.expansion_terms(PLACEHOLDER, _entries(tmp_path, fil_term=PLACEHOLDER, fil_source="A source", fil_reviewer="A reviewer")) == ["acceptable", "use", "policy"]


@pytest.mark.parametrize("query,expands", [
    ("zzqone zzqtwo", True),
    ("before ZZQONE   ZzqTwo, after", True),
    ("zzqvariant here", True),
    ("zzqone", False),
    ("zzqtwo zzqone", False),
    ("zzqone zzqtwoextra", False),
    ("xzzqone zzqtwo", False),
    ("zzqone zzqtwo-extra", False),
])
def test_phrases_match_whole_and_ignore_case(tmp_path, query, expands):
    entries = _entries(tmp_path, fil_term="zzqone zzqtwo", fil_variants=" zzqvariant ; ", fil_source="A source", fil_reviewer="A reviewer")
    assert bool(glossary.expansion_terms(query, entries)) is expands


def test_the_switch_is_on_by_default_and_runs_record_it(monkeypatch):
    assert config.USE_GLOSSARY is True
    assert metrics.settings()["use_glossary"] is True
    monkeypatch.setattr(config, "USE_GLOSSARY", False)
    assert metrics.settings()["use_glossary"] is False


@pytest.fixture(scope="module")
def searcher():
    return Searcher()


def _same(a, b):
    assert a.query_terms == b.query_terms and a.features == b.features and a.confidence == b.confidence
    assert [(h.chunk["chunk_id"], h.score, h.matched) for h in a.hits] == [(h.chunk["chunk_id"], h.score, h.matched) for h in b.hits]
    assert [(n, h.chunk["chunk_id"], h.score) for n, h in a.side] == [(n, h.chunk["chunk_id"], h.score) for n, h in b.side]


@needs_index
@pytest.mark.parametrize("query", ["data sharing agreement", PLACEHOLDER])
def test_results_are_identical_on_and_off_when_no_rows_are_filled(searcher, monkeypatch, tmp_path, query):
    path = tmp_path / "empty.csv"
    glossary.write_rows([_row("Acceptable Use Policy"), _row("Access Controls")], path)
    assert glossary.load_expansions(path) == []
    monkeypatch.setitem(searcher.__dict__, "glossary_entries", glossary.load_expansions(path))
    _same(searcher.search(query, use_glossary=True), searcher.search(query, use_glossary=False))


@needs_index
def test_a_placeholder_expands_keywords_only_when_on(searcher, monkeypatch, tmp_path):
    entries = _entries(tmp_path, fil_term=PLACEHOLDER, fil_source="A source", fil_reviewer="A reviewer")
    monkeypatch.setitem(searcher.__dict__, "glossary_entries", entries)
    keyword_calls, embedded = [], []
    real_score, real_encode = bm25.score, searcher.embedder.encode_query
    monkeypatch.setattr(bm25, "score", lambda index, terms: keyword_calls.append(list(terms)) or real_score(index, terms))
    monkeypatch.setattr(searcher.embedder, "encode_query", lambda text: embedded.append(text) or real_encode(text))

    off = searcher.search(PLACEHOLDER, use_glossary=False)
    on = searcher.search(PLACEHOLDER, use_glossary=True)

    assert keyword_calls == [[PLACEHOLDER], [PLACEHOLDER, "acceptable", "use", "policy"]]
    assert embedded == [PLACEHOLDER, PLACEHOLDER]
    assert on.query_terms == off.query_terms == [PLACEHOLDER]
    assert on.features["term_coverage"] == off.features["term_coverage"] == 0.0
    assert all(h.matched == [] for h in on.hits)
    assert on.hits[0].score > off.hits[0].score


@needs_index
def test_filled_rows_change_nothing_while_the_switch_is_off(searcher, monkeypatch, tmp_path):
    query = "data sharing agreement"
    before = searcher.search(query, use_glossary=False)
    entries = _entries(tmp_path, fil_term="data sharing", fil_source="A source", fil_reviewer="A reviewer")
    monkeypatch.setitem(searcher.__dict__, "glossary_entries", entries)
    _same(searcher.search(query, use_glossary=False), before)
