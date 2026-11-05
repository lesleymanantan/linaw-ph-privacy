#!/usr/bin/env python3
"""Write reports/abbreviation_sources.csv: where the corpus gives each hint's full name.

Reads the abbr.* rows of data/i18n/labels.csv. Each must appear next to its full name in a passage, as
"Full Name (ABBR)" or as a definition such as "Full Name" or "ABBR". The draft circular is used only if no
other document has it, because it is not law. Stops with an error if any hint has no source.
"""
import csv
import json
import re
import sys

from ph_privacy_guide.answer.labels import load_labels
from ph_privacy_guide.config import PROCESSED, REPORTS

OUT = REPORTS / "abbreviation_sources.csv"


def flatten(text: str) -> str:
    """Join hyphenated line breaks, as search does, and collapse the remaining white space."""
    return re.sub(r"\s+", " ", re.sub(r"([a-z])-\n([a-z])", r"\1\2", text))


def find_source(abbr: str, name: str, chunks: list[dict]) -> dict | None:
    name_pattern = r"\s*".join(re.escape(word) for word in name.split())
    pattern = re.compile(rf"(?i:{name_pattern})[’\'”\"]*,?\s*(?:or\s+(?:the\s+)?[“\"]?|\(\s*[“\"]?){abbr}s?\b[”\"]?\)?")
    ordered = sorted(chunks, key=lambda c: c["status"] == "draft")
    for chunk in ordered:
        match = pattern.search(flatten(chunk["text"]))
        if match:
            return {"abbreviation": abbr, "full_name": name, "citation": chunk["citation"], "quote": match.group(0)}
    return None


def main() -> int:
    with open(PROCESSED / "chunks.jsonl") as f:
        chunks = [json.loads(line) for line in f]
    hints = {k.split(".", 1)[1]: v["en"] for k, v in load_labels().items() if k.startswith("abbr.")}
    found = {abbr: find_source(abbr, name, chunks) for abbr, name in sorted(hints.items(), key=lambda kv: kv[0].lower())}
    missing = [abbr for abbr, source in found.items() if source is None]
    if missing:
        print(f"No source in the corpus for: {missing}")
        return 1
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["abbreviation", "full_name", "citation", "quote"], lineterminator="\n")
        w.writeheader()
        w.writerows(found.values())
    print(f"{len(found)} abbreviations, each with a source, written to {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
