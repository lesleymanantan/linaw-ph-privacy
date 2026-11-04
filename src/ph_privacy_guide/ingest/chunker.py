"""Turn section records into chunks.jsonl and validate the result.

Usage: python -m ph_privacy_guide.ingest.chunker
Run ph_privacy_guide.ingest.sectioner first.

Writes:
  data/processed/chunks.jsonl            one record per chunk (gitignored)
  data/processed/chunk_validation.md     checks and per-document summary

One chunk per section, or per subsection when a section is over MAX_WORDS. Definition sections are
always split, one chunk per defined term. Where there are no subsections, long text is packed into
paragraph groups. `text` is verbatim; `index_text` adds the heading and re-joins hyphenated line
breaks for search only. Annex 1 of Circular 2022-04 is never split.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections import Counter

from ph_privacy_guide import catalogue
from ph_privacy_guide.answer.warnings import annotation_warnings, status_warnings
from ph_privacy_guide.config import (ANNOTATION_LABEL, DRAFT_LABEL, PROCESSED, REPEALED_FOOTNOTE_WARNINGS,
                                     SEARCHABLE_KINDS, SUMMARY_LABEL, allowed_pdfs)
from ph_privacy_guide.ingest.sectioner import WHOLE_DOC_TYPES, _marker_re, nonspace_len

MAX_WORDS = 350
MIN_LEAD_WORDS = 15
CHUNKS = PROCESSED / "chunks.jsonl"
DEFINITION_RE = re.compile(r"definition", re.I)
INLINE_FIRST_ITEM_RE = re.compile(r"^(.*?[.–—-]\s*)(\(a\)\s.*)$")

_alpha = lambda c: chr(ord(c) + 1)
_num = lambda c: str(int(c) + 1)
STYLES = [
    (re.compile(r"^\(([a-z])\)\s*"), "a", _alpha),
    (re.compile(r"^\(([A-Z])\)\s*"), "A", _alpha),
    (re.compile(r"^\((\d{1,2})\)\s*"), "1", _num),
    (re.compile(r"^([A-Z])\.\s+"), "A", _alpha),
    (re.compile(r"^([a-z])\.\s*"), "a", _alpha),
    (re.compile(r"^(\d{1,2})\.\)?\s+"), "1", _num),
]


def words(text: str) -> int:
    return len(text.split())


def _join_words(lines: list[str]) -> int:
    return sum(words(l) for l in lines)


def find_items(lines: list[str]) -> list[tuple[int, str]]:
    """Line index and label of the first complete run of sequential list markers."""
    for i, line in enumerate(lines):
        for rx, first, step in STYLES:
            m = rx.match(line)
            if m and m.group(1) == first:
                items = [(i, first)]
                expected = step(first)
                for j in range(i + 1, len(lines)):
                    mj = rx.match(lines[j])
                    if mj and mj.group(1) == expected:
                        items.append((j, expected))
                        expected = step(expected)
                if len(items) >= 2:
                    return items
    return []


def _paragraphs(lines: list[str]) -> list[list[str]]:
    """Group lines into paragraphs: a short line ending in punctuation closes a paragraph."""
    width = max((len(l) for l in lines), default=0)
    out, cur = [], []
    for line in lines:
        cur.append(line)
        if line.rstrip()[-1:] in ".;:?" and len(line) < 0.85 * width:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _pack(lines: list[str], limit: int) -> list[list[str]]:
    groups, cur = [], []
    for para in _paragraphs(lines):
        pieces = [para] if _join_words(para) <= limit else [[l] for l in para]
        for piece in pieces:
            if cur and _join_words(cur) + _join_words(piece) > limit:
                groups.append(cur)
                cur = []
            cur.extend(piece)
    if cur:
        groups.append(cur)
    return groups


def split_lines(lines: list[str], limit: int = MAX_WORDS, force: bool = False, suffix: str = "") -> list[tuple[str, list[str]]]:
    """Return (suffix, lines) pieces. Suffixes read like (g) or (g)(1), or ", part 2" for text."""
    if not force and _join_words(lines) <= limit:
        return [(suffix, lines)]
    m = INLINE_FIRST_ITEM_RE.match(lines[0]) if lines else None
    if m:
        lines = [m.group(1).rstrip(), m.group(2)] + lines[1:]
    # An item's own marker is on its first line, so nested lists are looked for after that line.
    search_from = 1 if suffix else 0
    items = [(i + search_from, v) for i, v in find_items(lines[search_from:])]
    if items:
        out: list[tuple[str, list[str]]] = []
        if items[0][0] > 0:
            out.extend(split_lines(lines[:items[0][0]], limit, False, suffix))
        for k, (start, value) in enumerate(items):
            end = items[k + 1][0] if k + 1 < len(items) else len(lines)
            out.extend(split_lines(lines[start:end], limit, False, f"{suffix}({value})"))
        return out
    if _join_words(lines) <= limit:
        return [(suffix, lines)]
    groups = _pack(lines, limit)
    return [(f"{suffix}, part {n}" if len(groups) > 1 else suffix, g) for n, g in enumerate(groups, 1)]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def index_text(title: str, division: str, text: str) -> str:
    joined = re.sub(r"([a-z])-\n([a-z])", r"\1\2", text)
    return " ".join(x for x in (title, division, joined) if x)


def _load_page_text(doc_id: str) -> dict[int, str]:
    with open(PROCESSED / "pages" / f"{doc_id}.jsonl") as f:
        return {r["page"]: r["text"] for r in map(json.loads, f)}


def _locate(piece: list[str], pages: dict[int, str], lo: int, hi: int) -> tuple[int, int]:
    """Pages a piece actually occupies, within its record's range. Falls back to the whole range."""
    first = next((n for n in range(lo, hi + 1) if piece[0].strip() in pages.get(n, "")), None)
    if first is None:
        return lo, hi
    last = next((n for n in range(first, hi + 1) if piece[-1].strip() in pages.get(n, "")), None)
    return first, last if last is not None else hi


def build_chunks() -> list[dict]:
    rows = catalogue.load()
    cites = {r["doc_id"]: r["short_cite"] for r in rows}
    chunks: list[dict] = []
    for row in rows:
        if row["in_corpus"] != "yes":
            continue
        with open(PROCESSED / "sections" / f"{row['doc_id']}.jsonl") as f:
            records = [json.loads(line) for line in f]
        notes = [r for r in records if r["kind"] == "footnote"]
        page_text = _load_page_text(row["doc_id"])
        doc_chunks: list[dict] = []
        parents: dict[tuple[str, str], list[dict]] = {}
        for rec in records:
            if rec["kind"] == "footnote":
                continue
            lines = rec["text"].split("\n")
            if row["type"] in WHOLE_DOC_TYPES or rec["kind"] in ("preamble", "signature"):
                pieces = [("", lines)]
            else:
                force = rec["kind"] in ("section", "part") and bool(DEFINITION_RE.search(rec["title"]))
                pieces = split_lines(lines, force=force)
            label_tail = f" ({rec['label']})" if rec["label"] else ""
            core = rec["citation"][: -len(label_tail)] if label_tail else rec["citation"]
            seen: Counter[str] = Counter()
            cursor = rec["page_start"]
            for position, (suffix, piece) in enumerate(pieces):
                # A bare heading ahead of its subsections has nothing to show, but ranks high for being short.
                heading_only = position == 0 and len(pieces) > 1 and not suffix and _join_words(piece) < MIN_LEAD_WORDS
                seen[suffix] += 1
                key = suffix if seen[suffix] == 1 else f"{suffix}-{seen[suffix]}"
                text = "\n".join(piece)
                base = f"{row['doc_id']}:{rec['kind']}:{_slug(rec['section'])}"
                is_draft_annex = rec["kind"] == "annex" and row["status"] == "draft"
                page_start, page_end = _locate(piece, page_text, cursor, rec["page_end"])
                cursor = page_start
                chunk = {
                    "chunk_id": base + (f":{_slug(key)}" if key else ""),
                    "doc_id": rec["doc_id"], "kind": rec["kind"], "instrument": rec["instrument"],
                    "short_cite": rec["short_cite"], "section": rec["section"], "subsection": suffix.strip(", "),
                    "title": rec["title"], "division": rec["division"],
                    "citation": f"{core}{' ' if rec['kind'] != 'section' and suffix.startswith('(') else ''}{suffix}{label_tail}",
                    "authority": rec["authority"], "status": rec["status"], "label": rec["label"],
                    "replaced_by": rec["replaced_by"], "supplemented_by": rec["supplemented_by"],
                    "date_issued": rec["date_issued"], "version": rec["version"], "collection": rec["collection"],
                    "page_start": page_start, "page_end": page_end,
                    "searchable": rec["kind"] in SEARCHABLE_KINDS and not is_draft_annex and not heading_only,
                    "switch": "draft_annex" if is_draft_annex else "",
                    "rank_tier": 1 if rec["kind"] == "summary" else 0,
                    "annotations": [], "text": text, "index_text": index_text(rec["title"], rec["division"], text),
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
                doc_chunks.append(chunk)
                parents.setdefault((rec["kind"], rec["section"]), []).append(chunk)
        for note in notes:
            family = parents.get((note["parent_kind"], note["parent_section"]), [])
            marker = _marker_re(int(note["section"]))
            holder = next((c for c in family if marker.search(c["text"])), family[0] if family else None)
            annotation = {"number": int(note["section"]), "label": ANNOTATION_LABEL, "text": note["text"],
                          "citation": note["citation"]}
            holder["annotations"].append(annotation)
            doc_chunks.append({
                **{k: holder[k] for k in ("doc_id", "instrument", "short_cite", "authority", "status", "replaced_by",
                                          "supplemented_by", "date_issued", "version", "collection")},
                "chunk_id": f"{holder['chunk_id']}:fn{note['section']}", "kind": "footnote",
                "section": note["parent_section"], "subsection": holder["subsection"],
                "title": note["title"], "division": "", "citation": note["citation"],
                "label": ANNOTATION_LABEL, "draft_label": note.get("draft_label", ""),
                "page_start": note["page_start"], "page_end": note["page_end"], "searchable": False, "switch": "",
                "rank_tier": 0, "parent_chunk_id": holder["chunk_id"], "annotations": [], "text": note["text"],
                "index_text": "", "text_sha256": hashlib.sha256(note["text"].encode()).hexdigest(),
            })
        for chunk in doc_chunks:
            chunk["warnings"] = status_warnings(chunk, cites) + annotation_warnings(row["type"], chunk["annotations"], cites)
        chunks.extend(doc_chunks)
    return chunks


def validate(chunks: list[dict]) -> list[dict]:
    rows = {r["doc_id"]: r for r in catalogue.load()}
    out: list[dict] = []

    def add(check: str, ok: bool, detail: str = "", review: bool = False) -> None:
        out.append({"check": check, "result": "PASS" if ok else ("REVIEW" if review else "FAIL"), "detail": detail})

    ids = [c["chunk_id"] for c in chunks]
    add("Chunk ids unique", len(ids) == len(set(ids)),
        f"{len(ids)} chunks" + "; duplicates: " + ", ".join(k for k, v in Counter(ids).items() if v > 1)[:300])

    docs = {c["doc_id"] for c in chunks}
    corpus = {r["doc_id"] for r in rows.values() if r["in_corpus"] == "yes"}
    add("Every corpus document has chunks, and nothing else does", docs == corpus, f"{len(docs)} of {len(corpus)} documents")
    allowed = {p.stem for p in allowed_pdfs()}
    add("Only allowlisted documents", docs <= allowed, "no chunk comes from outside the four collection folders")

    required = ("doc_id", "instrument", "short_cite", "citation", "authority", "status", "version", "collection", "text")
    missing = [c["chunk_id"] for c in chunks if any(not c[k] for k in required) or c["page_start"] is None]
    add("Required metadata present", not missing, f"{len(missing)} chunks missing fields {missing[:5]}")
    no_date = sorted({c["doc_id"] for c in chunks if not c["date_issued"]})
    add("Issue date present", set(no_date) <= {"DRAFT_Updated_PIA_Guidelines_Circular", "NPC_Toolkit_Ch2_PIA_0618"},
        f"blank only where the document has none: {no_date}")
    empty_tag = [c["chunk_id"] for c in chunks if c["kind"] == "section" and not c["section"]]
    add("Section chunks carry a section number", not empty_tag, f"{len(empty_tag)} without")

    over = [c for c in chunks if c["searchable"] and words(c["text"]) > MAX_WORDS]
    whole = {c["chunk_id"] for c in over if rows[c["doc_id"]]["type"] in WHOLE_DOC_TYPES}
    bad = [f"{c['chunk_id']} ({words(c['text'])})" for c in over if c["chunk_id"] not in whole]
    add(f"Searchable chunks at most {MAX_WORDS} words", not bad,
        f"exceptions kept whole by design: {sorted(whole) or 'none'}; over limit: {bad[:8] or 'none'}")

    # No text lost or duplicated between section records and chunks.
    by_doc: dict[str, int] = Counter()
    for c in chunks:
        by_doc[c["doc_id"]] += nonspace_len(c["text"])
    diffs = {}
    for doc in corpus:
        with open(PROCESSED / "sections" / f"{doc}.jsonl") as f:
            source = sum(nonspace_len(json.loads(line)["text"]) for line in f)
        if source != by_doc[doc]:
            diffs[doc] = source - by_doc[doc]
    add("Chunk text adds up to section text", not diffs, f"differences {diffs or 'none'}")

    # Every chunk line appears verbatim on the page it came from.
    page_lines: dict[str, list[str]] = {}
    for doc in corpus:
        with open(PROCESSED / "pages" / f"{doc}.jsonl") as f:
            page_lines[doc] = [ln for line in f for ln in json.loads(line)["text"].split("\n")]
    joined = {d: "\n".join(v) for d, v in page_lines.items()}
    not_verbatim = [c["chunk_id"] for c in chunks for ln in c["text"].split("\n") if ln.strip() and ln.strip() not in joined[c["doc_id"]]]
    add("Every chunk line is verbatim source text", not not_verbatim, f"{len(not_verbatim)} lines differ {not_verbatim[:5]}")

    draft = [c for c in chunks if c["collection"] == "drafts"]
    bad = [c["chunk_id"] for c in draft if DRAFT_LABEL not in c["citation"] or c["status"] != "draft"
           or c["authority"] != "draft" or not any(DRAFT_LABEL in w for w in c["warnings"])]
    add(f'Every draft chunk says "{DRAFT_LABEL}"', not bad and bool(draft), f"{len(draft)} chunks, {len(bad)} unlabelled")
    other = [c["chunk_id"] for c in chunks if c["collection"] != "drafts" and DRAFT_LABEL in c["citation"]]
    add("No draft label elsewhere", not other, f"{len(other)} wrongly labelled")

    annex = [c for c in chunks if c["switch"] == "draft_annex"]
    add("Draft Annex A not searchable by default", bool(annex) and not any(c["searchable"] for c in annex), f"{len(annex)} chunks behind the switch")

    summary = [c for c in chunks if c["kind"] == "summary"]
    add("16-03 Summary labelled and ranked below sections",
        bool(summary) and all(c["rank_tier"] == 1 and c["label"] == SUMMARY_LABEL for c in summary)
        and {c["doc_id"] for c in summary} == {"NPC_Circular_16-03_Breach_Management"}, f"{len(summary)} chunks")

    notes = [c for c in chunks if c["kind"] == "footnote"]
    ids_set = set(ids)
    unlinked = [c["chunk_id"] for c in notes if c.get("parent_chunk_id") not in ids_set]
    wrong = [c["chunk_id"] for c in notes if c["label"] != ANNOTATION_LABEL or c["searchable"]]
    by_id = {c["chunk_id"]: c for c in chunks}
    on_signature = [c["chunk_id"] for c in notes if by_id.get(c.get("parent_chunk_id"), {}).get("kind") == "signature"]
    add("No footnote linked to a signature block", not on_signature, f"{len(on_signature)} linked")
    add("Footnotes linked, labelled and shown under their section", not unlinked and not wrong,
        f"{len(notes)} footnotes; {len(unlinked)} unlinked; {len(wrong)} mislabelled")
    with_notes = sum(len(c["annotations"]) for c in chunks)
    add("Every footnote attached to a chunk's annotations", with_notes == len(notes), f"{with_notes} attached")

    # The configured repealed-circular warning fires for every IRR footnote that cites it.
    pattern = next(iter(REPEALED_FOOTNOTE_WARNINGS))
    irr_notes = [c for c in notes if c["doc_id"] == "IRR_RA10173"]
    citing = [c for c in irr_notes if re.search(pattern, re.sub(r"\s+", " ", c["text"]))]
    warned = [c for c in chunks if c["doc_id"] == "IRR_RA10173" and any("17-01" in w and "2022-04" in w for w in c["warnings"])]
    warned_notes = sum(sum("17-01" in w for w in c["warnings"]) for c in warned)
    add("IRR chunks with notes citing 17-01 warn and name 2022-04", bool(citing) and warned_notes == len(citing),
        f"{len(citing)} notes cite 17-01, on {len(warned)} chunks: {[c['citation'] for c in warned]}")

    supp = [c for c in chunks if c["doc_id"] == "NPC_Circular_16-03_Breach_Management" and c["kind"] != "footnote"]
    add("16-03 chunks show Supplemented by Advisory 2026-02", all(any("Advisory 2026-02" in w for w in c["warnings"]) for c in supp), f"{len(supp)} chunks")

    toolkit = [c for c in chunks if c["doc_id"] == "NPC_Toolkit_Ch2_PIA_0618" and c["kind"] != "footnote"]
    add("Toolkit tagged guidance, with its label", all(c["authority"] == "guidance" and "educational" in c["label"] for c in toolkit), f"{len(toolkit)} chunks")

    annex1 = [c for c in chunks if c["doc_id"] == "NPC_Circular_2022-04_Annex1"]
    add("Annex 1 kept as one chunk", len(annex1) == 1, f"{len(annex1)} chunk, {words(annex1[0]['text'])} words" if annex1 else "missing")

    # Each chunk's first line must be on the page its citation gives.
    page_cache = {doc: _load_page_text(doc) for doc in corpus}
    misplaced = [c["chunk_id"] for c in chunks if c["text"].split("\n")[0].strip()
                 not in page_cache[c["doc_id"]].get(c["page_start"], "")]
    add("Each chunk starts on the page it cites", not misplaced, f"{len(misplaced)} misplaced {misplaced[:5]}")

    repealed_text = [c["chunk_id"] for c in chunks if c["status"] == "repealed"]
    add("Repealed instruments have no text in the corpus", not repealed_text, "17-01, 16-01, 16-02 and Advisory 2020-04 are catalogue rows only")
    return out


def write_report(chunks: list[dict], checks: list[dict]) -> str:
    tally = Counter(c["result"] for c in checks)
    searchable = [c for c in chunks if c["searchable"]]
    w = [words(c["text"]) for c in searchable]
    md = ["# Chunk validation report", "",
          f"**Checks: {tally['PASS']} pass, {tally['FAIL']} fail, {tally['REVIEW']} to review.**", "",
          f"{len(chunks)} chunks, {len(searchable)} searchable. Searchable chunk words: min {min(w)}, "
          f"median {int(statistics.median(w))}, max {max(w)}.", "",
          "| Result | Check | Detail |", "|---|---|---|"]
    md += [f"| {c['result']} | {c['check']} | {c['detail']} |" for c in checks]
    md += ["", "## Per-document summary", "",
           "| Document | Authority | Status | Chunks | Searchable | Footnotes | Median words | Max words |",
           "|---|---|---|---:|---:|---:|---:|---:|"]
    order = list(dict.fromkeys(c["doc_id"] for c in chunks))
    for doc in order:
        cs = [c for c in chunks if c["doc_id"] == doc]
        sw = [words(c["text"]) for c in cs if c["searchable"]] or [0]
        md.append(f"| {doc} | {cs[0]['authority']} | {cs[0]['status']} | {len(cs)} | {sum(c['searchable'] for c in cs)} | "
                  f"{sum(c['kind'] == 'footnote' for c in cs)} | {int(statistics.median(sw))} | {max(sw)} |")
    text = "\n".join(md) + "\n"
    (PROCESSED / "chunk_validation.md").write_text(text)
    return text


def main() -> None:
    chunks = build_chunks()
    with open(CHUNKS, "w") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(write_report(chunks, validate(chunks)))


if __name__ == "__main__":
    main()
