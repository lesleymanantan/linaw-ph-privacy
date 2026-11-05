"""The English-Filipino glossary: keeping and importing people's terms, and keyword expansion.

English terms come from the corpus (scripts/build_glossary.py). Filipino values come only from a CSV written by
people (scripts/import_glossary.py). This code copies those values as given and never creates or translates one.

Expansion runs only when the search asks for it (USE_GLOSSARY in config.py). A row expands only if fil_term and
fil_reviewer are filled. A Filipino term or variant must appear in the question as a whole phrase; upper and lower
case are ignored. Its English term's tokens are then added to the keyword search terms only.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Pattern

from ph_privacy_guide.config import GLOSSARY_CSV
from ph_privacy_guide.index import bm25

COLUMNS = ["en_term", "en_source_citation", "en_source_chunk_id", "n_sources", "fil_term", "fil_variants",
           "fil_source", "fil_reviewer"]
FIL_COLUMNS = ["fil_term", "fil_variants", "fil_source", "fil_reviewer"]
IMPORT_COLUMNS = ["en_term", *FIL_COLUMNS]
IGNORED_COLUMN_PREFIX = "ref_"
VARIANT_SEPARATOR = ";"


def _key(term: str) -> str:
    return term.strip().casefold()


def read_rows(path: Path = GLOSSARY_CSV) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict], path: Path = GLOSSARY_CSV) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_rows(rows: list[dict]) -> list[str]:
    """Problems in glossary rows: a filled fil_term needs a fil_source, and other fil_ values need a fil_term."""
    errors = []
    for row in rows:
        if row["fil_term"] and not row["fil_source"]:
            errors.append(f"{row['en_term']}: fil_term has no fil_source")
        if not row["fil_term"] and any(row[c] for c in FIL_COLUMNS):
            errors.append(f"{row['en_term']}: fil_ values with no fil_term")
    return errors


def keep_filipino(new_rows: list[dict], existing: list[dict]) -> tuple[list[dict], list[str]]:
    """Copy fil_ values from existing rows onto rebuilt rows, matching en_term. A term that would lose its values is an error."""
    by_term = {_key(row["en_term"]): row for row in existing}
    merged = [{**row, **{c: by_term.get(_key(row["en_term"]), {}).get(c, "") for c in FIL_COLUMNS}} for row in new_rows]
    rebuilt = {_key(row["en_term"]) for row in new_rows}
    errors = [f"{row['en_term']}: has Filipino values but is no longer in the rebuilt list"
              for row in existing if _key(row["en_term"]) not in rebuilt and any(row[c] for c in FIL_COLUMNS)]
    return merged, errors


@dataclass
class ImportReport:
    errors: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    imported: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    written: bool = False


def import_csv(source: Path, path: Path = GLOSSARY_CSV) -> ImportReport:
    """Validate the whole input first. If any row is invalid, nothing is written. Unmatched rows are listed, not written."""
    report = ImportReport()
    rows = read_rows(path)
    by_term = {_key(row["en_term"]): row for row in rows}
    with open(source, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        used = [c for c in (reader.fieldnames or []) if not c.startswith(IGNORED_COLUMN_PREFIX)]
        missing = [c for c in IMPORT_COLUMNS if c not in used]
        unexpected = [c for c in used if c not in IMPORT_COLUMNS]
        if missing:
            report.errors.append(f"missing columns: {', '.join(missing)}")
        if unexpected:
            report.errors.append(f"unexpected columns: {', '.join(unexpected)}")
        if report.errors:
            return report
        updates: dict[str, dict] = {}
        for raw in reader:
            line = reader.line_num
            if None in raw:
                report.errors.append(f"line {line}: more cells than columns")
                continue
            row = {c: (raw[c] or "").strip() for c in IMPORT_COLUMNS}
            if not row["fil_term"]:
                report.skipped.append(f"line {line}: {row['en_term']}")
                continue
            key = _key(row["en_term"])
            if not key:
                report.errors.append(f"line {line}: fil_term has no en_term")
            if not row["fil_source"]:
                report.errors.append(f"line {line}: {row['en_term']}: fil_term has no fil_source")
            if VARIANT_SEPARATOR in row["fil_term"]:
                report.errors.append(f"line {line}: {row['en_term']}: fil_term holds \"{VARIANT_SEPARATOR}\"; variants go in fil_variants")
            if key in updates:
                report.errors.append(f"line {line}: {row['en_term']}: appears more than once")
            if key and key not in by_term:
                report.unmatched.append(f"line {line}: {row['en_term']}")
                continue
            updates[key] = row
    if report.errors:
        return report
    for key, row in updates.items():
        target = by_term[key]
        if target["fil_term"]:
            report.replaced.append(target["en_term"])
        report.imported.append(target["en_term"])
        target.update({c: row[c] for c in FIL_COLUMNS})
    report.errors = validate_rows(rows)
    if report.errors or not updates:
        return report
    write_rows(rows, path)
    report.written = True
    return report


def _normal(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _phrase_pattern(phrase: str) -> Pattern[str]:
    """A whole phrase: any run of spaces between words, and no letter, digit or hyphen touching either end."""
    words = r"\s+".join(re.escape(word) for word in _normal(phrase).split())
    return re.compile(rf"(?<![\w-]){words}(?![\w-])")


def load_expansions(path: Path = GLOSSARY_CSV) -> list[tuple[Pattern[str], list[str]]]:
    """(phrase pattern, English keyword tokens) for each term and variant of the reviewed rows."""
    entries = []
    for row in read_rows(path):
        if not row["fil_term"].strip() or not row["fil_reviewer"].strip():
            continue
        phrases = [row["fil_term"], *row["fil_variants"].split(VARIANT_SEPARATOR)]
        tokens = bm25.tokenize(row["en_term"])
        entries += [(_phrase_pattern(phrase), tokens) for phrase in phrases if phrase.strip()]
    return entries


def expansion_terms(query: str, entries: list[tuple[Pattern[str], list[str]]]) -> list[str]:
    """English keyword tokens for every glossary phrase found in the question."""
    text = _normal(query)
    return list(dict.fromkeys(token for pattern, tokens in entries if pattern.search(text) for token in tokens))
