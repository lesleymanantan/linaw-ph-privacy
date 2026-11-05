"""Question schema enforcement and CSV import. Contains no questions."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ph_privacy_guide.config import PROCESSED, ROOT

QUESTIONS_DIR = ROOT / "eval" / "questions"
SPLITS = ("train", "dev", "test")
LANGUAGES = {"en", "fil", "taglish"}
TYPES = {"lookup", "scenario", "out_of_scope"}
SOURCES = {"human", "rule"}
ORIGINS = {"human", "ai_draft_edited"}
FIELDS = ["id", "split", "question", "language", "type", "answerable", "gold", "gold_doc_ids", "source", "origin",
          "author", "reviewer", "date", "pair_id"]
CSV_COLUMNS = ["id", "question", "language", "pair_id", "type", "answerable", "gold", "origin", "writer", "reviewer", "date",
               "notes"]
IGNORED_COLUMNS = {"notes"}
ANSWERABLE_VALUES = {"yes": True, "no": False}


def load_chunks() -> dict[str, dict]:
    with open(PROCESSED / "chunks.jsonl") as f:
        return {c["chunk_id"]: c for c in map(json.loads, f)}


def resolve_label(label: str, chunks: dict[str, dict]) -> list[str]:
    """Chunk ids for a gold label such as 'NPC_Circular_2022-04 s.7'. Any chunk of that section counts."""
    return [cid for cid, c in chunks.items()
            if c.get("gold_label") and (c["gold_label"] == label or c["gold_label"].startswith(label + "("))
            and (c["searchable"] or c["switch"])]


def resolve_gold_ids(row: dict, chunks: dict[str, dict]) -> set[str]:
    return {cid for label in row["gold"] for cid in resolve_label(label, chunks)}


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
        errs.append(f"answerable must be yes or no, not {row['answerable']!r}")
    elif row["answerable"] and row["type"] == "out_of_scope":
        errs.append("answerable must be no for out_of_scope")
    if row["answerable"] is True and not row["gold"]:
        errs.append("answerable question has no gold")
    if row["answerable"] is False and row["gold"]:
        errs.append("unanswerable question has gold")
    for label in row["gold"]:
        if not resolve_label(label, chunks):
            errs.append(f"gold label does not resolve to a searchable passage: {label}")
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


def split_gold_cell(cell: str) -> list[str]:
    return [p.strip() for p in cell.split(";") if p.strip()]


def csv_to_rows(path: Path, split: str, chunks: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Map the owner's columns to the schema: writer becomes author, source is human, notes are not read.

    A row with an empty question is skipped, however much else is filled in.
    """
    rows, errs = [], []  # unresolved gold is caught by validate_row, and fails the whole import
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        absent = [c for c in CSV_COLUMNS if c not in columns]
        unknown = [c for c in columns if c not in CSV_COLUMNS]
        if absent or unknown:
            return [], [f"CSV columns differ: missing {absent}, unknown {unknown}"]
        for raw in reader:
            line = reader.line_num
            if raw.get(None):
                errs.append(f"line {line}: more cells than columns")
                continue
            cell = {c: (raw[c] or "").strip() for c in CSV_COLUMNS if c not in IGNORED_COLUMNS}
            if not cell["question"]:
                continue
            gold = split_gold_cell(cell["gold"])
            rows.append({
                "id": cell["id"], "split": split, "question": cell["question"],
                "language": cell["language"], "type": cell["type"],
                "answerable": ANSWERABLE_VALUES.get(cell["answerable"], cell["answerable"]),
                "gold": gold, "gold_doc_ids": sorted({chunks[c]["doc_id"] for g in gold for c in resolve_label(g, chunks)}),
                "source": "human", "origin": cell["origin"], "author": cell["writer"], "reviewer": cell["reviewer"],
                "date": cell["date"], "pair_id": cell["pair_id"],
            })
    return rows, errs


def skipped_rows(path: Path) -> list[str]:
    """The rows an import skips for having no question, other than fully blank ones, by id or line number."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [(raw.get("id") or "").strip() or f"line {reader.line_num}" for raw in reader
                if not (raw.get("question") or "").strip() and not raw.get(None)
                and any((raw.get(c) or "").strip() for c in CSV_COLUMNS if c not in IGNORED_COLUMNS)]


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
