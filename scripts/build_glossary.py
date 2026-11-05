#!/usr/bin/env python3
"""Write data/glossary/en_fil_terms.csv: English defined terms from the corpus, keeping existing Filipino values.

Reads definition chunks from chunks.jsonl. Skips the draft circular, because it is not law. No Filipino
term is ever generated here: fil_ values are kept from the existing file, matching en_term. If a term with
Filipino values is no longer found, nothing is written.
"""
import json
import re
import sys

from ph_privacy_guide import glossary
from ph_privacy_guide.config import GLOSSARY_CSV as OUT
from ph_privacy_guide.config import PROCESSED, ROOT

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
    rows = []
    for key in sorted(found):
        sources = sorted(found[key], key=lambda c: (AUTHORITY_ORDER[c["authority"]], c["date_issued"]))
        best = sources[0]
        rows.append({"en_term": best["_term"], "en_source_citation": best["citation"],
                     "en_source_chunk_id": best["chunk_id"], "n_sources": len(sources)})
    rows, errors = glossary.keep_filipino(rows, glossary.read_rows(OUT) if OUT.exists() else [])
    if errors:
        sys.exit("Nothing was written:\n" + "\n".join(errors))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    glossary.write_rows(rows, OUT)
    kept = sum(1 for row in rows if row["fil_term"])
    print(f"{len(rows)} English terms written to {OUT.relative_to(ROOT)}; Filipino values kept on {kept}")


if __name__ == "__main__":
    main()
