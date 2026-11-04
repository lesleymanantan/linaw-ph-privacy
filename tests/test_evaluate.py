"""Evaluation tooling. Rows here are placeholders, not questions: the repository holds no questions."""
import csv
import json
import subprocess
import sys

import pytest

from ph_privacy_guide.config import ROOT
from ph_privacy_guide.evaluate import metrics
from ph_privacy_guide.evaluate import questions as Q

CHUNKS = {"c1": {"doc_id": "D1", "kind": "section", "citation": "Cite 1"},
          "c2": {"doc_id": "D2", "kind": "section", "citation": "Cite 2"},
          "c3": {"doc_id": "D2", "kind": "footnote", "citation": "Note"}}


def row(**over):
    base = {"id": "PLACEHOLDER-1", "split": "dev", "question": "PLACEHOLDER", "language": "en", "type": "definition",
            "answerable": True, "gold": ["c1"], "gold_doc_ids": ["D1"], "source": "human", "origin": "human",
            "author": "a", "reviewer": "r", "pair_id": "", "topic": "", "notes": ""}
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
    ({"gold": ["missing"]}, "does not exist"),
    ({"gold": ["c3"]}, "never searchable"),
    ({"answerable": False}, "unanswerable question has gold"),
    ({"type": "out_of_scope"}, "answerable must be false"),
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
    base = {"id": "PLACEHOLDER-1", "question": "PLACEHOLDER", "language": "fil", "type": "definition", "answerable": "true",
            "gold": "Cite 1; c2", "source": "", "origin": "human", "author": "a", "reviewer": "r", "pair_id": "", "topic": "", "notes": ""}
    return {**base, **over}


def test_import_resolves_citations_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [_csv_row()])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert errs == []
    written = Q.load_split("dev", tmp_path)[0]
    assert written["gold"] == ["c1", "c2"] and written["gold_doc_ids"] == ["D1", "D2"]
    assert written["source"] == "human" and out.name == "dev.jsonl"


def test_import_writes_nothing_if_any_row_is_bad(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    _write_csv(tmp_path / "in.csv", [_csv_row(), _csv_row(id="PLACEHOLDER-2", gold="nowhere")])
    out, errs = Q.import_csv(tmp_path / "in.csv", "dev", tmp_path)
    assert out is None and errs and not (tmp_path / "dev.jsonl").exists()


def test_frozen_test_split_cannot_be_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "load_chunks", lambda: CHUNKS)
    (tmp_path / "test.sha256").write_text("x\n")
    _write_csv(tmp_path / "in.csv", [_csv_row()])
    out, errs = Q.import_csv(tmp_path / "in.csv", "test", tmp_path)
    assert out is None and "frozen" in errs[0]


def _s(language="en", answerable=True, rank=None, not_sure=False):
    return {"id": "x", "language": language, "answerable": answerable, "not_sure": not_sure, "gold_rank": rank, "top": []}


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


def test_gold_rank_uses_the_order_shown():
    assert metrics.score_question(row(gold=["b"]), ["a", "b"], False)["gold_rank"] == 2


def test_dev_command_takes_no_file_argument():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate.py"), "eval/questions/test.jsonl"],
                         capture_output=True, text=True)
    assert out.returncode != 0 and "takes no arguments" in out.stderr


def test_dev_command_says_when_there_are_no_questions():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate.py")], capture_output=True, text=True)
    assert out.returncode == 1 and "No dev questions" in out.stdout


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
