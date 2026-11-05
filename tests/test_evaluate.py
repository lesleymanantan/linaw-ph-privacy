"""Evaluation tooling. Rows here are placeholders, not questions: the repository holds no questions."""
import csv
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ph_privacy_guide import config
from ph_privacy_guide.config import ROOT
from ph_privacy_guide.evaluate import metrics
from ph_privacy_guide.evaluate import questions as Q

def _chunk(doc, label, searchable=True, switch=""):
    return {"doc_id": doc, "gold_label": label, "searchable": searchable, "switch": switch}


CHUNKS = {"c1": _chunk("D1", "D1 s.1"), "c2": _chunk("D2", "D2 s.2"),
          "c3a": _chunk("D2", "D2 s.3(a)"), "c3b": _chunk("D2", "D2 s.3(b)"), "c12": _chunk("D2", "D2 s.12"),
          "c9": _chunk("D2", "D2 s.9", searchable=False), "c8": _chunk("D3", "D3 annex", searchable=False, switch="draft_annex")}


def row(**over):
    base = {"id": "PLACEHOLDER-1", "split": "dev", "question": "PLACEHOLDER", "language": "en", "type": "lookup",
            "answerable": True, "gold": ["D1 s.1"], "gold_doc_ids": ["D1"], "source": "human", "origin": "human",
            "author": "a", "reviewer": "r", "date": "", "pair_id": ""}
    return {**base, **over}


def test_repository_holds_no_questions():
    assert Q.load_split("train") == [] and Q.load_split("dev") == [] and Q.load_split("test") == []


def test_schema_file_matches_code():
    schema = json.loads((ROOT / "eval" / "question_schema.json").read_text())
    assert set(schema["required"]) == set(Q.FIELDS)
    assert set(schema["properties"]["language"]["enum"]) == Q.LANGUAGES
    assert set(schema["properties"]["type"]["enum"]) == Q.TYPES


def test_csv_template_matches_code():
    with open(ROOT / "eval" / "questions_template.csv") as f:
        assert next(csv.reader(f)) == Q.CSV_COLUMNS


def test_valid_row_passes():
    assert Q.validate_row(row(), CHUNKS) == []


@pytest.mark.parametrize("over,needle", [
    ({"split": "test", "origin": "ai_draft_edited"}, "only origin=human"),
    ({"reviewer": ""}, "reviewer is required"),
    ({"language": "xx"}, "bad language"),
    ({"gold": []}, "no gold"),
    ({"gold": ["D1 s.99"]}, "does not resolve"),
    ({"gold": ["D2 s.9"]}, "does not resolve"),
    ({"answerable": False}, "unanswerable question has gold"),
    ({"type": "out_of_scope"}, "answerable must be no"),
    ({"type": "definition"}, "bad type"),
    ({"language": "tl"}, "bad language"),
    ({"answerable": "maybe"}, "answerable must be yes or no"),
    ({"source": "rule"}, "train only"),
    ({"origin": ""}, "origin must be"),
])
def test_invalid_rows_are_rejected(over, needle):
    assert any(needle in e for e in Q.validate_row(row(**over), CHUNKS))


def test_rule_rows_allowed_in_train_only():
    assert Q.validate_row(row(split="train", source="rule", origin="", reviewer=""), CHUNKS) == []


def test_pair_may_not_cross_splits():
    errs = Q.validate_set([row(pair_id="P")], CHUNKS, [row(id="PLACEHOLDER-2", split="train", pair_id="P")])
    assert any("crosses splits" in e for e in errs)


def _write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=Q.CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def _csv_row(**over):
    base = {"id": "PLACEHOLDER-1", "question": "PLACEHOLDER", "language": "fil", "pair_id": "P1", "type": "lookup", "answerable": "yes",
            "gold": "D1 s.1; D2 s.2", "origin": "human", "writer": "w", "reviewer": "r", "date": "D", "notes": "N"}
    return {**base, **over}


def test_label_resolves_to_any_chunk_of_its_section():
    assert Q.resolve_label("D2 s.3", CHUNKS) == ["c3a", "c3b"]
    assert Q.resolve_label("D2 s.3(a)", CHUNKS) == ["c3a"]
    assert Q.resolve_label("D1 s.1", CHUNKS) == ["c1"]  # not s.12 of anything
    assert Q.resolve_label("D2 s.1", CHUNKS) == []  # s.12 does not count for s.1
    assert Q.resolve_label("D3 annex", CHUNKS) == ["c8"]


def test_label_from_the_owners_example_resolves_on_the_real_corpus():
    chunks = Q.load_chunks()
    assert Q.resolve_label("NPC_Circular_2022-04 s.7", chunks)
    assert Q.resolve_label("RA10173 s.3(l)", chunks)
    assert len(Q.resolve_label("RA10173 s.3", chunks)) > 10


def test_import_resolves_labels_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [_csv_row()])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert errs == []
    written = Q.load_split("dev", tmp_path)[0]
    assert written["gold"] == ["D1 s.1", "D2 s.2"] and written["gold_doc_ids"] == ["D1", "D2"]
    assert written["source"] == "human" and out.name == "dev.jsonl"
    assert written["author"] == "w" and written["date"] == "D" and written["pair_id"] == "P1" and written["answerable"] is True
    assert set(written) == set(Q.FIELDS) and "N" not in written.values()


def test_template_has_the_owners_columns_and_no_rows():
    lines = (ROOT / "eval" / "questions_template.csv").read_text().splitlines()
    assert lines == ["id,question,language,pair_id,type,answerable,gold,origin,writer,reviewer,date,notes"]
    assert lines[0].split(",") == Q.CSV_COLUMNS


def test_import_skips_blank_rows_and_ignores_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    blank = {c: "" for c in Q.CSV_COLUMNS}
    notes_only = {**blank, "notes": "N"}
    _write_csv(tmp_path / "in.csv", [blank, _csv_row(), notes_only, blank])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert errs == [] and len(Q.load_split("dev", tmp_path)) == 1


def test_import_skips_half_filled_rows_and_lists_them(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    empty = {c: "" for c in Q.CSV_COLUMNS}
    half = [{**empty, "id": f"PLACEHOLDER-{n}", "writer": "w"} for n in (4, 5, 6)]
    full = [_csv_row(id=f"PLACEHOLDER-{n}") for n in (1, 2, 3)]
    _write_csv(tmp_path / "in.csv", full[:1] + half[:1] + full[1:] + half[1:] + [empty])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert errs == []
    assert [r["id"] for r in Q.load_split("dev", tmp_path)] == ["PLACEHOLDER-1", "PLACEHOLDER-2", "PLACEHOLDER-3"]
    assert Q.skipped_rows(tmp_path / "in.csv") == ["PLACEHOLDER-4", "PLACEHOLDER-5", "PLACEHOLDER-6"]


def test_a_filled_row_missing_something_else_still_fails_the_import(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [_csv_row(), _csv_row(id="PLACEHOLDER-2", language="")])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert out is None and any("bad language" in e for e in errs)


def test_import_of_only_blank_rows_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [{c: "" for c in Q.CSV_COLUMNS}])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert out is None and errs == ["the CSV has no rows"]


@pytest.mark.parametrize("over,needle", [
    ({"answerable": "true"}, "answerable must be yes or no"),
    ({"answerable": ""}, "answerable must be yes or no"),
    ({"type": "definition"}, "bad type"),
    ({"origin": ""}, "origin must be"),
])
def test_import_rejects_values_outside_the_allowed_lists(tmp_path, monkeypatch, over, needle):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [_csv_row(**over)])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert out is None and any(needle in e for e in errs)


def test_unanswerable_rows_need_no_gold_and_may_be_any_type(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [_csv_row(id="PLACEHOLDER-1", type="out_of_scope", answerable="no", gold=""),
                                     _csv_row(id="PLACEHOLDER-2", type="scenario", answerable="no", gold="")])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert errs == [] and [r["answerable"] for r in Q.load_split("dev", tmp_path)] == [False, False]


def test_import_rejects_old_or_extra_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    (tmp_path / "in.csv").write_text("id,question,language,type,answerable,gold,source,origin,author,reviewer,pair_id,topic,notes\n")
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert out is None and "missing" in errs[0] and "topic" in errs[0]


def test_import_handles_short_and_overlong_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    header = ",".join(Q.CSV_COLUMNS)
    (tmp_path / "in.csv").write_text(f"{header}\nPLACEHOLDER-1,PLACEHOLDER\n,,,,,,,,,,,,extra\n")
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert out is None and any("more cells than columns" in e for e in errs) and any("PLACEHOLDER-1" in e for e in errs)


def test_import_writes_nothing_if_any_row_is_bad(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [_csv_row(), _csv_row(id="PLACEHOLDER-2", gold="D9 s.1")])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert out is None and errs and not (tmp_path / "dev.jsonl").exists()


def test_frozen_test_split_cannot_be_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    (tmp_path / "test.sha256").write_text("x\n")
    _write_csv(tmp_path / "in.csv", [_csv_row()])
    out, errs = Q.import_csv(tmp_path / "in.csv", "test", tmp_path)
    assert out is None and "frozen" in errs[0]


def _s(language="en", answerable=True, rank=None, not_sure=False, confidence=0.5):
    features = dict.fromkeys(config.CONFIDENCE_WEIGHTS, confidence)
    return {"id": "x", "language": language, "answerable": answerable, "not_sure": not_sure, "gold_rank": rank, "top": [],
            "confidence": confidence, "features": features}


def test_recall_and_mrr():
    m = metrics.summarise([_s(rank=1), _s(rank=2), _s(rank=5), _s(rank=None)])
    assert m["recall@1"] == 0.25 and m["recall@3"] == 0.5 and m["recall@5"] == 0.75
    assert m["mrr"] == pytest.approx(round((1 + 0.5 + 0.2 + 0) / 4, 4))


def test_abstention_and_false_confident():
    scored = [_s(answerable=False, not_sure=True), _s(answerable=False, not_sure=False),
              _s(rank=1), _s(rank=4), _s(rank=2, not_sure=True)]
    m = metrics.summarise(scored)
    assert m["abstention_rate"] == 0.5
    assert m["over_abstention_rate"] == pytest.approx(round(1 / 3, 4))
    # Answered: one unanswerable (wrong), rank 1 (right), rank 4 (wrong: not in the top 3).
    assert m["false_confident_rate"] == pytest.approx(round(2 / 3, 4))


def test_language_groups_are_separate():
    groups = metrics.summarise_groups([_s(language="en", rank=1), _s(language="fil", rank=None)])
    assert groups["en"]["recall@1"] == 1.0 and groups["fil"]["recall@1"] == 0.0 and groups["all"]["n"] == 2
    assert groups["taglish"]["n"] == 0 and groups["taglish"]["recall@1"] is None


def _result(main, side=()):
    hit = lambda cid: SimpleNamespace(chunk={"chunk_id": cid})
    return SimpleNamespace(hits=[hit(c) for c in main], side=[("pending", hit(c)) for c in side], not_sure=False, confidence=0.5, features={})


def test_gold_rank_counts_any_chunk_of_the_section():
    assert metrics.score_question(row(), {"b", "z"}, _result(["a", "b"]))["gold_rank"] == 2


def test_side_block_hit_is_recorded_but_not_counted_in_recall():
    scored = metrics.score_question(row(), {"d"}, _result(["a"], side=["d"]))
    assert scored["gold_rank"] is None and scored["gold_in_side_block"] is True


def test_sweep_applies_thresholds_per_language_and_sets_nothing():
    scored = [_s(language="en", rank=1, confidence=0.9), _s(language="fil", rank=None, confidence=0.2),
              _s(language="fil", answerable=False, confidence=0.1)]
    before = config.NOT_SURE_CONFIDENCE_THRESHOLD
    table = metrics.sweep(scored, thresholds=[0.0, 0.5])
    assert table["en"][1]["shown_share"] == 1.0
    assert table["fil"][0]["shown_share"] == 1.0 and table["fil"][1]["shown_share"] == 0.0
    assert table["fil"][1]["abstention_rate"] == 1.0
    assert config.NOT_SURE_CONFIDENCE_THRESHOLD == before


def test_feature_means_split_right_from_wrong():
    means = metrics.feature_means([_s(rank=1, confidence=0.9), _s(rank=None, confidence=0.1)])
    assert means["all"]["right"]["top_cosine"] == 0.9 and means["all"]["wrong"]["top_cosine"] == 0.1


def test_dev_command_takes_no_file_argument():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate.py"), "eval/questions/test.jsonl"],
                         capture_output=True, text=True)
    assert out.returncode != 0 and "takes no arguments" in out.stderr


def test_dev_command_says_when_there_are_no_questions():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate.py")], capture_output=True, text=True)
    assert out.returncode == 1 and "No dev questions" in out.stdout


def test_confidence_report_takes_no_file_argument_and_needs_dev():
    script = str(ROOT / "scripts" / "confidence_report.py")
    out = subprocess.run([sys.executable, script, "eval/questions/test.jsonl"], capture_output=True, text=True)
    assert out.returncode != 0 and "takes no arguments" in out.stderr
    out = subprocess.run([sys.executable, script], capture_output=True, text=True)
    assert out.returncode == 1 and "No dev questions" in out.stdout


def test_final_refuses_while_no_threshold_is_set(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(metrics.config, "NOT_SURE_CONFIDENCE_THRESHOLD", None)
    assert metrics.run_final(True, search=lambda _: None, root=tmp_path, directory=tmp_path, results_dir=tmp_path) == 2
    assert "NOT_SURE_CONFIDENCE_THRESHOLD" in capsys.readouterr().out


def test_final_needs_the_flag(tmp_path, capsys):
    assert metrics.run_final(False, search=lambda _: None, root=tmp_path, directory=tmp_path) == 2
    assert "--final" in capsys.readouterr().out


def _repo(tmp_path):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    directory = tmp_path / "eval"
    directory.mkdir()
    data = directory / "test.jsonl"
    data.write_text(json.dumps(row(id="PLACEHOLDER-T", split="test")) + "\n")
    return git, directory, data


def test_final_refuses_without_a_hash_file(tmp_path):
    _, directory, _ = _repo(tmp_path)
    _, problems = metrics.final_preconditions(tmp_path, directory, tmp_path / "results")
    assert any("test.sha256 does not exist" in p for p in problems)


def test_final_refuses_uncommitted_files(tmp_path):
    _, directory, data = _repo(tmp_path)
    (directory / "test.sha256").write_text(metrics.file_sha256(data) + "\n")
    _, problems = metrics.final_preconditions(tmp_path, directory, tmp_path / "results")
    assert any("not committed" in p for p in problems)


def test_final_passes_when_committed_then_refuses_edits_and_second_runs(tmp_path):
    git, directory, data = _repo(tmp_path)
    (directory / "test.sha256").write_text(metrics.file_sha256(data) + "\n")
    git("add", "-A")
    git("commit", "-qm", "freeze")
    digest, problems = metrics.final_preconditions(tmp_path, directory, tmp_path / "results")
    assert problems == [] and digest == metrics.file_sha256(data)

    results = tmp_path / "results"
    results.mkdir()
    (results / f"final_{digest[:12]}_abc.json").write_text("{}")
    _, problems = metrics.final_preconditions(tmp_path, directory, results)
    assert any("runs once" in p for p in problems)

    data.write_text(data.read_text() + "\n")
    _, problems = metrics.final_preconditions(tmp_path, directory, tmp_path / "other")
    assert any("differs" in p for p in problems) and any("hash mismatch" in p for p in problems)
