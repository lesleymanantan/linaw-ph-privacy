"""Split RA 10173, the IRR and the circulars into section records, and validate them.

Usage: python -m ph_privacy_guide.ingest.sectioner
Run ph_privacy_guide.ingest.extract first.

Writes:
  data/processed/sections/<doc_id>.jsonl   preamble / section / trailer / annex records (gitignored)
  data/processed/section_validation.md     checks, summary and per-document details
  data/processed/section_validation.csv    one row per record

Section text is verbatim page text in reading order, minus repeated page headers and footers
(and margin line numbers in the draft). Line breaks are kept. Subsection and definition-level
splitting is a later chunking step. Advisories and the toolkit are not handled here yet.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from ph_privacy_guide import catalogue
from ph_privacy_guide.config import DRAFT_LABEL, PROCESSED

SECTIONED_TYPES = {"statute", "irr", "circular", "draft_circular"}
WHOLE_DOC_TYPES = {"annex"}

# Project owner's stated section count, checked and reported. Never adjusted to fit the text: a
# mismatch is a FAIL for a human to resolve.
STATED_SECTION_COUNT = {"RA10173_DPA_2012": 44}
EFFECTIVITY_TITLE_RE = re.compile(r"effectivity", re.I)
EFFECTIVITY_TEXT_RE = re.compile(r"takes?\s+effect", re.I)

# The dot after SEC is optional: RA 10173 prints s.22 as "SEC 22."
HEADING_RE = re.compile(r"^(?:SECTION|Section|SEC\.?|Sec\.?)\s*(\d+)\s*\.\s*(?:[-–—]\s*)?(.*)$")
# Starts like a heading but failed HEADING_RE, and is followed by a capital rather than a cross-reference.
MISSED_START_RE = re.compile(r"^(?:SECTION|Section|SEC\.?|Sec\.?)\s*\d+\b\s*[:\-–—]?\s*[A-Z]")
XREF_START_RE = re.compile(r"^(?:SECTION|Section|SEC\.?|Sec\.?)\s*\d+\b")
# Heading-shaped text in the middle of a line (sentence-ending cross-references also match; for review).
MIDLINE_RE = re.compile(r"\S\s+((?:SECTION|Section|SEC\.?|Sec\.?)\s*\d+\s*\.\s+[A-Z][a-z]+)")
STRUCT_RE = re.compile(r"^(CHAPTER|RULE|Chapter|Rule)\s+([IVXLC]+)\s*\.?\s*(.*)$")
TITLE_END_RE = re.compile(r"(.+?)(?:\.\s*[-–—]\s*|\s[-–—]\s?|\.\s|\.$)")
TOC_RE = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
TRAILER_RE = re.compile(r"^(Approved\b|SGD\b|\(Sgd\.?\)|SO ORDERED|This Act which is a consolidation)")
FOOTNOTE_RE = re.compile(r"^\d{1,2}\s+[A-Z“\"]")
LINE_NO_RE = re.compile(r"^\d{1,3}(?:\s+|$)")
MAX_LINE_NO_STEP = 15
MAX_TITLE_WORDS = 20
SHORT_WORDS, LONG_WORDS = 10, 350


@dataclass
class Line:
    page: int
    text: str


@dataclass
class Clean:
    lines: list[Line]
    stripped_boilerplate: dict[str, int]
    page_count: int
    kept_numbered: list[str]
    stripped_line_numbers: bool
    raw_chars: int
    stripped_chars: int


def nonspace_len(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip())


def clean_pages(pages: list[tuple[int, str]]) -> Clean:
    """Remove margin line numbers (if the document has them) and repeated page furniture."""
    split = [(n, [ln.rstrip() for ln in t.split("\n") if ln.strip()]) for n, t in pages]
    raw_chars = sum(nonspace_len(t) for _, t in pages)
    all_lines = [ln for _, ls in split for ln in ls]
    has_ln = bool(all_lines) and sum(bool(LINE_NO_RE.match(ln)) for ln in all_lines) / len(all_lines) > 0.5
    kept_numbered: list[str] = []
    if has_ln:
        # Margin numbers run continuously through the document. Strip a number only if it continues
        # that run; anything else (footnote markers, table cells) is document text and must stay.
        prev = 0
        new_split = []
        for n, ls in split:
            out = []
            for ln in ls:
                m = LINE_NO_RE.match(ln)
                if m and prev < int(m.group().strip()) <= prev + MAX_LINE_NO_STEP:
                    prev = int(m.group().strip())
                    rest = ln[m.end():].strip()
                    if rest:
                        out.append(rest)
                else:
                    if m:
                        kept_numbered.append(f"p{n}: {ln[:60]}")
                    out.append(ln)
            new_split.append((n, out))
        split = new_split

    threshold = max(2, math.ceil(0.6 * len(split)))
    counts: Counter[str] = Counter()
    for _, ls in split:
        counts.update({_norm(ln) for ln in ls[:4] + ls[-5:]})
    furniture = {k for k, v in counts.items() if v >= threshold and k}

    lines: list[Line] = []
    stripped: Counter[str] = Counter()
    for n, ls in split:
        last = len(ls) - 1
        for i, ln in enumerate(ls):
            at_edge = i < 4 or i > last - 5
            bare_page_no = at_edge and re.fullmatch(r"(?:Page\s*)?\d{1,3}(?:\s*of\s*\d{1,3})?", ln.strip())
            if at_edge and (_norm(ln) in furniture or bare_page_no):
                stripped[_norm(ln)] += 1
                continue
            lines.append(Line(n, ln))
    kept = sum(nonspace_len(l.text) for l in lines)
    return Clean(lines, dict(sorted(stripped.items())), len(split), kept_numbered, has_ln, raw_chars, raw_chars - kept)


def longest_increasing(nums: list[int]) -> set[int]:
    """Indexes of the longest strictly increasing subsequence, preferring earlier occurrences."""
    if not nums:
        return set()
    best = [1] * len(nums)
    nxt = [-1] * len(nums)
    for i in range(len(nums) - 1, -1, -1):
        for j in range(i + 1, len(nums)):
            if nums[j] > nums[i] and best[j] + 1 > best[i]:
                best[i], nxt[i] = best[j] + 1, j
    i = max(range(len(nums)), key=lambda k: (best[k], -k))
    keep = set()
    while i != -1:
        keep.add(i)
        i = nxt[i]
    return keep


@dataclass
class DocResult:
    doc_id: str
    records: list[dict] = field(default_factory=list)
    numbers: list[int] = field(default_factory=list)
    gaps: list[int] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    out_of_sequence: list[str] = field(default_factory=list)
    possible_missed: list[str] = field(default_factory=list)
    midline_mentions: list[str] = field(default_factory=list)
    xrefs_dismissed: int = 0
    toc: list[tuple[int, str]] = field(default_factory=list)
    footnote_lines: int = 0
    clean: Clean | None = None
    accounted_chars: int = 0
    problems: list[str] = field(default_factory=list)


def _title(lines: list[Line], rest: str, i: int) -> str:
    """Section title: heading text up to its closing full stop or dash, may run onto the next line."""
    candidate = rest
    if i + 1 < len(lines):
        candidate = f"{rest} {lines[i + 1].text}".strip()
    m = TITLE_END_RE.match(candidate)
    return (m.group(1) if m else candidate).strip()


def toc_entries(lines: list[Line], first_heading: int) -> list[tuple[int, str]]:
    return [(int(m.group(1)), m.group(2)) for l in lines[:first_heading] if (m := TOC_RE.match(l.text))]


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _base(row: dict, kind: str, section: str, title: str, chapter: str, chunk: list[Line]) -> dict:
    cite = row["short_cite"]
    if kind == "section":
        cite = f"{cite}, s.{section}"
    label = DRAFT_LABEL if row["status"] == "draft" else ""
    return {
        "doc_id": row["doc_id"], "kind": kind, "section": section, "title": title, "division": chapter,
        "citation": f"{cite} ({label})" if label else cite,
        "authority": row["authority"], "status": row["status"], "label": label,
        "replaced_by": row["replaced_by"], "supplemented_by": row["supplemented_by"],
        "date_issued": row["date_issued"], "version": row["version"], "collection": row["collection"],
        "page_start": chunk[0].page if chunk else None, "page_end": chunk[-1].page if chunk else None,
        "text": "\n".join(l.text for l in chunk),
    }


def section_document(row: dict, pages: list[tuple[int, str]]) -> DocResult:
    res = DocResult(row["doc_id"])
    res.clean = clean = clean_pages(pages)
    lines = clean.lines
    res.footnote_lines = sum(bool(FOOTNOTE_RE.match(l.text)) for l in lines)

    if row["type"] in WHOLE_DOC_TYPES:
        res.records.append(_base(row, "annex", "annex", row["title"], "", lines))
        res.accounted_chars = nonspace_len(res.records[0]["text"])
        return res

    cands: list[tuple[int, int, str]] = []  # line index, number, rest
    for i, l in enumerate(lines):
        if m := HEADING_RE.match(l.text):
            cands.append((i, int(m.group(1)), m.group(2)))
        elif MISSED_START_RE.match(l.text):
            res.possible_missed.append(f"p{l.page}: {l.text[:90]}")
        elif XREF_START_RE.match(l.text):
            res.xrefs_dismissed += 1
        if m := MIDLINE_RE.search(l.text):
            res.midline_mentions.append(f"p{l.page}: …{m.group(1)}")
    keep = longest_increasing([c[1] for c in cands])
    accepted = [c for k, c in enumerate(cands) if k in keep]
    accepted_nums = {c[1] for c in accepted}
    for k, (i, num, _) in enumerate(cands):
        if k not in keep:
            note = f"p{lines[i].page}: {lines[i].text[:90]}"
            (res.duplicates if num in accepted_nums else res.out_of_sequence).append(note)

    res.numbers = [c[1] for c in accepted]
    if res.numbers:
        res.gaps = sorted(set(range(1, res.numbers[-1] + 1)) - accepted_nums)
    else:
        res.problems.append("no section headings detected")
        return res

    first = accepted[0][0]
    res.toc = toc_entries(lines, first) if row["type"] == "irr" else []

    # Walk lines, pulling Chapter/Rule headings out as context.
    bounds = [c[0] for c in accepted] + [len(lines)]
    struct_lines: set[int] = set()
    divisions: dict[int, str] = {}
    current = ""
    heading_idx = set(bounds)
    i = 0
    while i < len(lines):
        if i in heading_idx:
            divisions[i] = current
        m = STRUCT_RE.match(lines[i].text)
        # A real division heading has a stop or nothing after the numeral, unlike "Rule IV of the IRR".
        if m and i not in heading_idx and (not m.group(3) or re.search(rf"{m.group(2)}\s*\.", lines[i].text)):
            struct_lines.add(i)
            title = [m.group(3)] if m.group(3) else []
            j = i + 1
            while not m.group(3) and j < len(lines) and j not in heading_idx and not STRUCT_RE.match(lines[j].text) \
                    and (lines[j].text.upper() == lines[j].text or j == i + 1) and len(lines[j].text) < 100:
                title.append(lines[j].text)
                struct_lines.add(j)
                j += 1
            current = f"{m.group(1).title()} {m.group(2)}" + (f": {' '.join(title)}" if title else "")
            i = j
            continue
        i += 1

    preamble = [l for k, l in enumerate(lines[:first]) if k not in struct_lines]
    if preamble:
        res.records.append(_base(row, "preamble", "preamble", "Preamble", "", preamble))
    for n, (start, num, rest) in enumerate(accepted):
        end = bounds[n + 1]
        body = [l for k, l in zip(range(start, end), lines[start:end]) if k not in struct_lines]
        trailer: list[Line] = []
        if n == len(accepted) - 1:
            for t, l in enumerate(body):
                if t and TRAILER_RE.match(l.text):
                    body, trailer = body[:t], body[t:]
                    break
        title = _title(lines, rest, start)
        rec = _base(row, "section", str(num), title, divisions.get(start, ""), body)
        res.records.append(rec)
        if len(title.split()) > MAX_TITLE_WORDS:
            res.problems.append(f"s.{num}: long title, check heading split: {title[:80]}")
        if trailer:
            res.records.append(_base(row, "trailer", "trailer", "Signatures and closing", "", trailer))
    res.accounted_chars = sum(nonspace_len(r["text"]) for r in res.records) + sum(
        nonspace_len(lines[k].text) for k in struct_lines)
    return res


def load_pages(doc_id: str) -> tuple[list[tuple[int, str]], list[int]]:
    pages, skipped = [], []
    with open(PROCESSED / "pages" / f"{doc_id}.jsonl") as f:
        for line in f:
            r = json.loads(line)
            if r["status"] == "ok":
                pages.append((r["page"], r["text"]))
            else:
                skipped.append(r["page"])
    return pages, skipped


def run() -> list[DocResult]:
    out_dir = PROCESSED / "sections"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for row in catalogue.load():
        if row["in_corpus"] != "yes" or row["type"] not in SECTIONED_TYPES | WHOLE_DOC_TYPES:
            continue
        pages, _ = load_pages(row["doc_id"])
        res = section_document(row, pages)
        with open(out_dir / f"{row['doc_id']}.jsonl", "w") as f:
            for rec in res.records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        results.append(res)
    return results


def _words(rec: dict) -> int:
    return len(rec["text"].split())


def _secs(res: DocResult) -> list[dict]:
    return [r for r in res.records if r["kind"] == "section"]


def _lost(res: DocResult) -> int:
    return res.clean.raw_chars - res.clean.stripped_chars - res.accounted_chars


def toc_differences(res: DocResult) -> tuple[list[str], list[str]]:
    """Compare the IRR's contents with its body. Returns (number differences, title differences).

    A contents title that is a prefix of the body title is a contents entry wrapped onto a second
    line, not a difference.
    """
    body = {int(r["section"]): r["title"] for r in _secs(res)}
    toc = dict(res.toc)
    numbers = [f"s.{n} only in table of contents" for n in sorted(set(toc) - set(body))]
    numbers += [f"s.{n} only in body" for n in sorted(set(body) - set(toc))]
    titles = [f"s.{n}: contents `{toc[n]}`, body `{body[n]}`" for n in sorted(set(toc) & set(body))
              if not _title_key(body[n]).startswith(_title_key(toc[n]))]
    return numbers, titles


def run_checks(results: list[DocResult], catalogue_rows: list[dict]) -> list[dict]:
    """Return one row per check per document: check, doc_id, result (PASS/FAIL/REVIEW), detail."""
    rows = {r["doc_id"]: r for r in catalogue_rows}
    out: list[dict] = []

    def add(check: str, doc_id: str, result: str, detail: str = "") -> None:
        out.append({"check": check, "doc_id": doc_id, "result": result, "detail": detail})

    for res in results:
        doc, row = res.doc_id, rows[res.doc_id]
        if row["type"] in WHOLE_DOC_TYPES:
            recs = res.records
            one = len(recs) == 1 and recs[0]["kind"] == "annex"
            add("Annex kept as one block", doc, "PASS" if one and _lost(res) == 0 else "FAIL",
                f"{len(recs)} record, pages {recs[0]['page_start']}-{recs[0]['page_end']}, "
                f"parent {row['parent_doc_id']}")
            continue
        expected = list(range(1, res.numbers[-1] + 1)) if res.numbers else []
        ok = bool(res.numbers) and res.numbers == expected and not res.duplicates and not res.out_of_sequence
        detail = f"1-{res.numbers[-1]}" if ok else (
            f"gaps {res.gaps}; duplicates {res.duplicates}; out of sequence {res.out_of_sequence}")
        add("Numbering: no gaps or duplicates", doc, "PASS" if ok else "FAIL", detail)

        add("Possible missed headings", doc, "FAIL" if res.possible_missed else "PASS",
            "; ".join(res.possible_missed) or f"none ({res.xrefs_dismissed} cross-references dismissed)")
        if res.midline_mentions:
            add("Heading-shaped text inside a line", doc, "REVIEW", "; ".join(res.midline_mentions))

        secs = _secs(res)
        eff = [r for r in secs if EFFECTIVITY_TITLE_RE.search(r["title"])]
        eff_ok = bool(eff) and bool(EFFECTIVITY_TEXT_RE.search(eff[-1]["text"]))
        add("Effectivity clause present", doc, "PASS" if eff_ok else "FAIL",
            f"s.{eff[-1]['section']} {eff[-1]['title']}" if eff else "no section titled Effectivity")

        if res.clean.stripped_line_numbers:
            add("Margin numbers removed, other numbers kept", doc, "PASS",
                f"{len(res.clean.kept_numbered)} number-led lines kept as text: "
                + "; ".join(res.clean.kept_numbered))
        over = {k: v for k, v in res.clean.stripped_boilerplate.items() if v > res.clean.page_count}
        if over:
            add("Page furniture not over-stripped", doc, "REVIEW", f"more removals than pages: {over}")

        if row["type"] == "irr":
            numbers, titles = toc_differences(res)
            add("Section numbers match own table of contents", doc, "FAIL" if numbers else "PASS",
                "; ".join(numbers) or f"{len(res.toc)} entries, all match")
            if titles:
                add("Section titles match own table of contents", doc, "REVIEW",
                    f"{len(titles)} worded differently in the document: " + "; ".join(titles))
        if doc in STATED_SECTION_COUNT:
            stated = STATED_SECTION_COUNT[doc]
            add(f"Has {stated} sections (as stated)", doc, "PASS" if len(secs) == stated else "FAIL",
                f"document has {len(secs)}; s.{secs[-2]['section']} {secs[-2]['title']}, "
                f"s.{secs[-1]['section']} {secs[-1]['title']}")

    for res in results:
        draft = rows[res.doc_id]["status"] == "draft"
        if draft:
            ok = bool(res.records) and all(
                r["label"] == DRAFT_LABEL and DRAFT_LABEL in r["citation"]
                and r["status"] == "draft" and r["authority"] == "draft" for r in res.records)
            add(f'Labelled "{DRAFT_LABEL}"', res.doc_id, "PASS" if ok else "FAIL",
                f"{len(res.records)} of {len(res.records)} records" if ok else "unlabelled records found")
        elif any(r["label"] for r in res.records):
            add("No draft label on non-draft text", res.doc_id, "FAIL", "draft label on non-draft document")
    for res in results:
        lost = _lost(res)
        if lost:
            add("All text accounted for", res.doc_id, "FAIL", f"{lost} characters unaccounted for")
    return out


def write_reports(results: list[DocResult], checks: list[dict]) -> str:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED / "section_validation.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["doc_id", "kind", "section", "title", "division", "page_start", "page_end", "words"])
        for res in results:
            for r in res.records:
                w.writerow([r["doc_id"], r["kind"], r["section"], r["title"], r["division"],
                            r["page_start"], r["page_end"], _words(r)])

    tally = Counter(c["result"] for c in checks)
    md = [
        "# Section validation report", "",
        "Generated by `python -m ph_privacy_guide.ingest.sectioner`. Covers RA 10173, the IRR, the circulars, "
        "the draft circular and Annex 1. Advisories and the toolkit are not sectioned yet.", "",
        f"**Checks: {tally['PASS']} pass, {tally['FAIL']} fail, {tally['REVIEW']} to review.**", "",
        "## Failures and items to review", "",
    ]
    flagged = [c for c in checks if c["result"] != "PASS"]
    md += ["| Result | Check | Document | Detail |", "|---|---|---|---|"]
    md += [f"| {c['result']} | {c['check']} | {c['doc_id']} | {c['detail']} |" for c in flagged]
    md += ["", "## Summary", "",
           f"Short = under {SHORT_WORDS} words. Long = over {LONG_WORDS} words, to be split at the chunking step. "
           "Footnote lines are possible footnote openings still inside section text.", "",
           "| Document | Sections | Gaps | Duplicates | Short | Long | Effectivity | Footnote lines | "
           "Trailer words | Lost chars |",
           "|---|---:|---|---:|---:|---:|---|---:|---:|---:|"]
    for res in results:
        secs = _secs(res)
        eff = [r for r in secs if EFFECTIVITY_TITLE_RE.search(r["title"])]
        trailer = sum(_words(r) for r in res.records if r["kind"] == "trailer")
        md.append(f"| {res.doc_id} | {len(secs) or 'one block'} | {', '.join(map(str, res.gaps)) or 'none'} | "
                  f"{len(res.duplicates)} | {sum(_words(r) < SHORT_WORDS for r in secs)} | "
                  f"{sum(_words(r) > LONG_WORDS for r in secs)} | {'s.' + eff[-1]['section'] if eff else '—'} | "
                  f"{res.footnote_lines} | {trailer} | {_lost(res)} |")
    md += ["", "## All checks", "", "| Result | Check | Document | Detail |", "|---|---|---|---|"]
    md += [f"| {c['result']} | {c['check']} | {c['doc_id']} | {c['detail']} |" for c in checks]
    md += ["", "## Per-document details", ""]
    for res in results:
        items = [f"problem: {p}" for p in res.problems]
        if res.clean.stripped_line_numbers:
            items.append("margin line numbers stripped")
        items += [f"rejected duplicate candidate: {d}" for d in res.duplicates]
        items += [f"rejected out-of-sequence candidate: {d}" for d in res.out_of_sequence]
        tr = [r for r in res.records if r["kind"] == "trailer"]
        if tr:
            items.append(f"trailer {_words(tr[0])} words, p{tr[0]['page_start']}-{tr[0]['page_end']}")
        items.append("page furniture stripped: " + ("; ".join(
            f"`{k[:60]}` x{v}" for k, v in res.clean.stripped_boilerplate.items()) or "none"))
        md.append(f"### {res.doc_id}")
        md += [f"- {i}" for i in items] + [""]
    text = "\n".join(md)
    (PROCESSED / "section_validation.md").write_text(text)
    return text


def main() -> None:
    results = run()
    checks = run_checks(results, catalogue.load())
    text = write_reports(results, checks)
    print(text[: text.index("## All checks")])


if __name__ == "__main__":
    main()
