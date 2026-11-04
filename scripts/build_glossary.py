#!/usr/bin/env python3
"""Write data/glossary/en_fil_terms.csv: English defined terms from the corpus, Filipino columns empty.

Reads definition chunks from chunks.jsonl. Skips the draft circular, because it is not law. No Filipino
term is ever generated here; people fill those columns in.
"""
import csv
import json
import re

from ph_privacy_guide.config import PROCESSED, ROOT

OUT = ROOT / "data" / "glossary" / "en_fil_terms.csv"
COLUMNS = ["en_term", "en_source_citation", "en_source_chunk_id", "n_sources", "fil_term", "fil_variants",
           "fil_source", "fil_reviewer"]
AUTHORITY_ORDER = {"statute": 0, "rule": 1, "guidance": 2, "policy": 3}
QUOTED_RE = re.compile(r"^\(?[A-Za-z]{1,2}[.)]\)?\s*[“\"]([^”\"]{2,80})[”\"]")
UNQUOTED_RE = re.compile(r"^\([a-z]\)\s+([A-Z][A-Za-z ,\-]{2,70}?)\s+(?:shall refer|refers?|is|means)\b")
DEFINITION_TITLE = re.compile(r"definition", re.I)


def defined_term(text: str) -> str | None:
    m = QUOTED_RE.match(text) or UNQUOTED_RE.match(text)
    return m.group(1).strip().rstrip(",") if m else None


def main() -> None:
    with open(PROCESSED / "chunks.jsonl") as f:
        chunks = [json.loads(line) for line in f]
    found: dict[str, list[dict]] = {}
    for c in chunks:
        if c["kind"] in ("section", "part") and c["status"] != "draft" and DEFINITION_TITLE.search(c["title"]) and c["subsection"]:
            term = defined_term(c["text"])
            if term:
                found.setdefault(term.casefold(), []).append({**c, "_term": term})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        for key in sorted(found):
            sources = sorted(found[key], key=lambda c: (AUTHORITY_ORDER[c["authority"]], c["date_issued"]))
            best = sources[0]
            w.writerow([best["_term"], best["citation"], best["chunk_id"], len(sources), "", "", "", ""])
    print(f"{len(found)} English terms written to {OUT.relative_to(ROOT)}; Filipino columns left empty")


if __name__ == "__main__":
    main()
