"""Question schema enforcement and CSV import. Contains no questions."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ph_privacy_guide.config import PROCESSED, ROOT, SEARCHABLE_KINDS

QUESTIONS_DIR = ROOT / "eval" / "questions"
SPLITS = ("train", "dev", "test")
LANGUAGES = {"en", "fil", "taglish"}
TYPES = {"definition", "obligation", "right", "procedure", "penalty", "scenario", "status", "out_of_scope", "not_covered"}
UNANSWERABLE_TYPES = {"out_of_scope", "not_covered"}
SOURCES = {"human", "rule"}
ORIGINS = {"human", "ai_draft_edited"}
FIELDS = ["id", "split", "question", "language", "type", "answerable", "gold", "gold_doc_ids", "source", "origin",
          "author", "reviewer", "pair_id", "topic", "notes"]
CSV_COLUMNS = ["id", "question", "language", "type", "answerable", "gold", "source", "origin", "author", "reviewer",
               "pair_id", "topic", "notes"]


def load_chunks() -> dict[str, dict]:
    with open(PROCESSED / "chunks.jsonl") as f:
        return {c["chunk_id"]: c for c in map(json.loads, f)}


def validate_row(row: dict, chunks: dict[str, dict]) -> list[str]:
    errs: list[str] = []
    missing = [f for f in FIELDS if f not in row]
    extra = [f for f in row if f not in FIELDS]
    if missing or extra:
        return [f"missing fields {missing}, unknown fields {extra}"]
    if not row["id"]:
        errs.append("id is empty")
    if row["split"] not in SPLITS:
        errs.append(f"bad split {row['split']!r}")
    if not row["question"].strip():
        errs.append("question is empty")
    if row["language"] not in LANGUAGES:
        errs.append(f"bad language {row['language']!r}")
    if row["type"] not in TYPES:
        errs.append(f"bad type {row['type']!r}")
    if not isinstance(row["answerable"], bool):
        errs.append("answerable must be true or false")
    elif row["answerable"] == (row["type"] in UNANSWERABLE_TYPES):
        errs.append("answerable must be false for out_of_scope and not_covered, and only for those")
    if row["answerable"] is True and not row["gold"]:
        errs.append("answerable question has no gold")
    if row["answerable"] is False and row["gold"]:
        errs.append("unanswerable question has gold")
    for g in row["gold"]:
        chunk = chunks.get(g)
        if chunk is None:
            errs.append(f"gold chunk does not exist: {g}")
        elif chunk["kind"] not in SEARCHABLE_KINDS:
            errs.append(f"gold chunk is never searchable: {g}")
    if row["source"] not in SOURCES:
        errs.append(f"bad source {row['source']!r}")
    if row["source"] == "rule":
        if row["split"] != "train":
            errs.append("source=rule rows are allowed in train only")
    elif row["origin"] not in ORIGINS:
        errs.append(f"origin must be human or ai_draft_edited, not {row['origin']!r}")
    if row["split"] == "test" and row["origin"] != "human":
        errs.append("the test split may contain only origin=human rows")
    if row["split"] in ("dev", "test") and row["source"] != "human":
        errs.append("dev and test rows must have source=human")
    if (row["split"] in ("dev", "test") or row["origin"] == "ai_draft_edited") and not row["reviewer"].strip():
        errs.append("reviewer is required")
    return errs


def validate_set(rows: list[dict], chunks: dict[str, dict], other_rows: list[dict] | None = None) -> list[str]:
    errs: list[str] = []
    seen: set[str] = set()
    for row in rows:
        label = row.get("id") or "(no id)"
        errs += [f"{label}: {e}" for e in validate_row(row, chunks)]
        if row.get("id") in seen:
            errs.append(f"{label}: duplicate id")
        seen.add(row.get("id"))
    other_rows = other_rows or []
    other_ids = {r["id"] for r in other_rows}
    errs += [f"{r['id']}: id already used in another split" for r in rows if r.get("id") in other_ids]
    other_pairs = {r["pair_id"] for r in other_rows if r["pair_id"]}
    errs += [f"{r['id']}: pair_id {r['pair_id']} crosses splits" for r in rows if r.get("pair_id") in other_pairs]
    return errs


def load_split(split: str, directory: Path = QUESTIONS_DIR) -> list[dict]:
    path = directory / f"{split}.jsonl"
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def resolve_gold(cell: str, chunks: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Gold cells hold citations as printed by the tool, or chunk ids, separated by ';'."""
    by_citation: dict[str, list[str]] = {}
    for cid, c in chunks.items():
        by_citation.setdefault(c["citation"], []).append(cid)
    ids, errs = [], []
    for item in filter(None, (p.strip() for p in cell.split(";"))):
        if item in chunks:
            ids.append(item)
        elif item in by_citation and len(by_citation[item]) == 1:
            ids.append(by_citation[item][0])
        elif item in by_citation:
            errs.append(f"citation matches several chunks, use a chunk id: {item}")
        else:
            errs.append(f"gold not found: {item}")
    return ids, errs


def csv_to_rows(path: Path, split: str, chunks: dict[str, dict]) -> tuple[list[dict], list[str]]:
    rows, errs = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        absent = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if absent:
            return [], [f"CSV is missing columns: {absent}"]
        for number, raw in enumerate(reader, 2):
            answerable = {"true": True, "false": False}.get(raw["answerable"].strip().lower(), raw["answerable"])
            gold, gold_errs = resolve_gold(raw["gold"], chunks)
            label = raw["id"].strip() or f"line {number}"
            errs += [f"{label}: {e}" for e in gold_errs]
            rows.append({
                "id": raw["id"].strip(), "split": split, "question": raw["question"].strip(),
                "language": raw["language"].strip(), "type": raw["type"].strip(), "answerable": answerable,
                "gold": gold, "gold_doc_ids": sorted({chunks[g]["doc_id"] for g in gold}),
                "source": raw["source"].strip() or "human", "origin": raw["origin"].strip(),
                "author": raw["author"].strip(), "reviewer": raw["reviewer"].strip(),
                "pair_id": raw["pair_id"].strip(), "topic": raw["topic"].strip(), "notes": raw["notes"].strip(),
            })
    return rows, errs


def write_split(rows: list[dict], split: str, directory: Path = QUESTIONS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{split}.jsonl"
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def import_csv(path: Path, split: str, directory: Path = QUESTIONS_DIR) -> tuple[Path | None, list[str]]:
    """All rows valid, or nothing is written. A frozen test split cannot be replaced."""
    if split not in SPLITS:
        return None, [f"bad split {split!r}"]
    if split == "test" and (directory / "test.sha256").exists():
        return None, ["the test split is frozen; it cannot be replaced by an import"]
    chunks = load_chunks()
    rows, errs = csv_to_rows(path, split, chunks)
    others = [r for s in SPLITS if s != split for r in load_split(s, directory)]
    errs += validate_set(rows, chunks, others)
    if not rows and not errs:
        errs.append("the CSV has no rows")
    if errs:
        return None, errs
    return write_split(rows, split, directory), []
