"""Split every document into section records and footnotes, and validate them.

Usage: python -m ph_privacy_guide.ingest.sectioner
Run ph_privacy_guide.ingest.extract first.

Writes:
  data/processed/sections/<doc_id>.jsonl   one record per preamble, section or part, footnote,
                                           signature block, annex or summary (gitignored)
  data/processed/section_validation.md     checks, summary and per-document details
  data/processed/section_validation.csv    one row per record

Text is verbatim page text in reading order, minus repeated page headers and footers and the
draft's margin line numbers. Line breaks are kept. Documents with numbered sections are split on
those. Documents without them fall back to titled parts; the chunker then splits long parts into
paragraphs. Subsection and definition-level splitting happens in the chunker.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from ph_privacy_guide import catalogue
from ph_privacy_guide.config import ANNOTATION_LABEL, DRAFT_LABEL, PROCESSED, SUMMARY_LABEL, TOOLKIT_LABEL

LAW_TYPES = {"statute", "irr", "circular", "draft_circular"}
GUIDANCE_TYPES = {"advisory", "joint_advisory", "toolkit"}
SECTIONED_TYPES = LAW_TYPES | GUIDANCE_TYPES
WHOLE_DOC_TYPES = {"annex"}

# Expected section count, from the project owner's check of the PDF. A mismatch is a FAIL.
STATED_SECTION_COUNT = {"RA10173_DPA_2012": 45}
# Numbers a document's own numbering skips, confirmed by reading the text. Reported, never hidden.
DOCUMENT_OWN_GAPS = {"NPC_Advisory_2024-01_Cross_Border_Clauses": [4, 5]}
EFFECTIVITY_TITLE_RE = re.compile(r"effectivity", re.I)
EFFECTIVITY_TEXT_RE = re.compile(r"takes?\s+effect", re.I)

# The dot after SEC is optional: RA 10173 prints s.22 as "SEC 22."
HEADING_RE = re.compile(r"^(?:SECTION|Section|SEC\.?|Sec\.?)\s*(\d+)\s*\.\s*(?:[-–—]\s*)?(.*)$")
# Starts like a heading but failed HEADING_RE, and is followed by a capital rather than a cross-reference.
MISSED_START_RE = re.compile(r"^(?:SECTION|Section|SEC\.?|Sec\.?)\s*\d+\b\s*[:\-–—]?\s*[A-Z]")
XREF_START_RE = re.compile(r"^(?:SECTION|Section|SEC\.?|Sec\.?)\s*\d+\b")
# Heading-shaped text in the middle of a line (sentence-ending cross-references also match).
MIDLINE_RE = re.compile(r"\S\s+((?:SECTION|Section|SEC\.?|Sec\.?)\s*\d+\s*\.\s+[A-Z][a-z]+)")
STRUCT_RE = re.compile(r"^(CHAPTER|RULE|Chapter|Rule)\s+([IVXLC]+)\s*\.?\s*(.*)$")
TITLE_END_RE = re.compile(r"(.+?)(?:\.\s*\d*\s*[-–—]\s*|\s[-–—]\s?|\.\s|\.$)")
TOC_RE = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
TRAILER_RE = re.compile(r"^(Approved\b|SGD\b|\(Sgd\.?\)|SO ORDERED|This Act which is a consolidation)")
EXTRA_RE = re.compile(r"^(Annex|ANNEX|Appendix|APPENDIX|Summary)\b")
LINE_NO_RE = re.compile(r"^\d{1,3}(?:\s+|$)")
FOOTNOTE_RE = re.compile(r"^(\d{1,3})(?:\s+|(?=[A-Z“\"]))(?![(\d])(\S.*)$")
WHEREAS_RE = re.compile(r"^(WHEREAS|WHEREFORE|NOW,? THEREFORE)\b")
ROMAN_HEAD_RE = re.compile(r"^[IVX]+\.\s+\S")
LIST_START_RE = re.compile(r"^(\(?[A-Za-z0-9]{1,3}[.)]|[•—–-])")
MAX_LINE_NO_STEP = 15
MAX_TITLE_WORDS = 20
MAX_PART_TITLE_WORDS = 9
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


@dataclass
class Footnote:
    number: int
    page: int
    lines: list[str]
    marker_index: int  # index into the body lines
    marker_found: bool


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

    # Headers on every page, or alternating between odd and even pages.
    threshold = max(2, math.ceil(0.6 * len(split)))
    alt_threshold = max(3, math.ceil(0.4 * len(split)))
    counts: Counter[str] = Counter()
    outer: Counter[str] = Counter()
    for _, ls in split:
        counts.update({_norm(ln) for ln in ls[:4] + ls[-5:]})
        outer.update({_norm(ln) for ln in ls[:2] + ls[-2:]})
    # Bare numbers are never furniture by repetition: they may be table cells. Page numbers are
    # handled below, only where they are the outermost line once the furniture is gone.
    furniture = {k for k, v in counts.items() if v >= threshold and k and k != "#"}
    furniture |= {k for k, v in outer.items() if v >= alt_threshold and k and k != "#"}

    lines: list[Line] = []
    stripped: Counter[str] = Counter()
    page_no = re.compile(r"(?:Page\s*)?\d{1,3}(?:\s*of\s*\d{1,3})?")
    for n, ls in split:
        last = len(ls) - 1
        rest = []
        for i, ln in enumerate(ls):
            if (i < 4 or i > last - 5) and _norm(ln) in furniture:
                stripped[_norm(ln)] += 1
            else:
                rest.append(ln)
        for edge in (0, -1):
            if rest and page_no.fullmatch(rest[edge].strip()):
                stripped[_norm(rest[edge])] += 1
                rest.pop(edge)
        lines.extend(Line(n, ln) for ln in rest)
    kept = sum(nonspace_len(l.text) for l in lines)
    return Clean(lines, dict(sorted(stripped.items())), len(split), kept_numbered, has_ln, raw_chars, raw_chars - kept)


def _marker_re(number: int) -> re.Pattern:
    # A superscript extracts as "word1" or "word.1", or with a space after punctuation.
    # A number after a line break, or one followed by a stop, is a list item, not a marker.
    return re.compile(rf"(?:[A-Za-z]{number}(?!\d)|[.,;:”\"’'\)\]] ?{number}(?![\d.]))")


def split_footnotes(lines: list[Line]) -> tuple[list[Line], list[Footnote]]:
    """Move footnotes out of the body. A footnote opens low on a page, carries the next number in
    the document's sequence, and has a matching marker in the body text above it on that page."""
    pages: dict[int, list[Line]] = {}
    for l in lines:
        pages.setdefault(l.page, []).append(l)
    body: list[Line] = []
    notes: list[Footnote] = []
    expected = 1
    for page, ls in pages.items():
        start = None
        for i, l in enumerate(ls):
            m = FOOTNOTE_RE.match(l.text)
            if not m or i < len(ls) * 0.25 or int(m.group(1)) not in range(expected, expected + 3):
                continue
            if any(_marker_re(int(m.group(1))).search(x.text) for x in ls[:i]):
                start = i
                break
        if start is None:
            body.extend(ls)
            continue
        offset = len(body)
        above = ls[:start]
        body.extend(above)
        current: Footnote | None = None
        for l in ls[start:]:
            m = FOOTNOTE_RE.match(l.text)
            opens = m and (current is None or int(m.group(1)) == current.number + 1)
            if opens:
                num = int(m.group(1))
                marker = max((k for k, x in enumerate(above) if _marker_re(num).search(x.text)), default=None)
                current = Footnote(num, page, [l.text],
                                   offset + (marker if marker is not None else max(len(above) - 1, 0)),
                                   marker is not None)
                notes.append(current)
                expected = num + 1
            else:
                current.lines.append(l.text)
    return body, notes


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
    footnotes: list[Footnote] = field(default_factory=list)
    fallback: bool = False
    clean: Clean | None = None
    accounted_chars: int = 0
    problems: list[str] = field(default_factory=list)


def _title(lines: list[Line], rest: str, i: int) -> str:
    """Section title: heading text up to its closing stop or dash; may run onto the next line."""
    candidate = rest
    if i + 1 < len(lines):
        candidate = f"{rest} {lines[i + 1].text}".strip()
    m = TITLE_END_RE.match(candidate)
    return (m.group(1) if m else candidate).strip()


def toc_entries(lines: list[Line], first_heading: int) -> list[tuple[int, str]]:
    return [(int(m.group(1)), m.group(2)) for l in lines[:first_heading] if (m := TOC_RE.match(l.text))]


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def doc_label(row: dict) -> str:
    if row["status"] == "draft":
        return DRAFT_LABEL
    if row["type"] == "toolkit":
        return TOOLKIT_LABEL
    return ""


def _base(row: dict, kind: str, section: str, title: str, division: str, chunk: list[Line], label: str | None = None) -> dict:
    cite = row["short_cite"]
    if kind == "section":
        cite = f"{cite}, s.{section}"
    elif kind in ("part", "annex", "summary") and row["type"] not in WHOLE_DOC_TYPES:
        cite = f"{cite}, {title}"
    label = doc_label(row) if label is None else label
    return {
        "doc_id": row["doc_id"], "kind": kind, "section": section, "title": title, "division": division,
        "citation": f"{cite} ({label})" if label else cite,
        "instrument": row["title"], "short_cite": row["short_cite"],
        "authority": row["authority"], "status": row["status"], "label": label,
        "replaced_by": row["replaced_by"], "clarified_by": row["clarified_by"],
        "date_issued": row["date_issued"], "version": row["version"], "collection": row["collection"],
        "page_start": chunk[0].page if chunk else None, "page_end": chunk[-1].page if chunk else None,
        "text": "\n".join(l.text for l in chunk),
    }


def _is_part_title(lines: list[Line], i: int, first: int) -> bool:
    """A short title-case line standing alone between sentences, or a Roman-numbered heading."""
    text = lines[i].text.strip()
    if ROMAN_HEAD_RE.match(text) and len(text.split()) <= MAX_PART_TITLE_WORDS + 2:
        return True
    words = text.split()
    if not 1 <= len(words) <= MAX_PART_TITLE_WORDS or text[-1] in ".;:,?!" or not text[0].isupper():
        return False
    if LIST_START_RE.match(text) or text.isupper():
        return False
    long_words = [w for w in words if len(w) > 3]
    if not long_words or sum(w[0].isupper() for w in long_words) / len(long_words) < 0.6:
        return False
    if i > first and lines[i - 1].text.rstrip()[-1] not in ".;:?)":
        return False
    return i + 1 < len(lines) and (lines[i + 1].text[0].isupper() or lines[i + 1].text[0] in "“\"")


def _part_bounds(lines: list[Line]) -> tuple[int, list[int]]:
    """For documents without numbered sections: end of the WHEREAS block, then titled part starts."""
    first = 0
    for i, l in enumerate(lines):
        if WHEREAS_RE.match(l.text):
            j = i
            while j + 1 < len(lines) and lines[j].text.rstrip()[-1] not in ";:.":
                j += 1
            first = j + 1
    starts = [i for i in range(first, len(lines)) if _is_part_title(lines, i, first)]
    # Where a document numbers its headings in Roman, title-case lines are table headers, not parts.
    roman = [i for i in starts if ROMAN_HEAD_RE.match(lines[i].text.strip())]
    if len(roman) >= 3:
        starts = roman
    # Text before the first heading is still document text: keep it as a part of its own.
    if not starts or starts[0] > first:
        starts = [first] + starts
    return first, starts


def _span(rec: dict, lo: int, hi: int) -> dict:
    rec["_span"] = (lo, hi)
    return rec


def section_document(row: dict, pages: list[tuple[int, str]]) -> DocResult:
    res = DocResult(row["doc_id"])
    res.clean = clean = clean_pages(pages)

    if row["type"] in WHOLE_DOC_TYPES:
        res.records.append(_base(row, "annex", "annex", row["title"], "", clean.lines))
        res.accounted_chars = nonspace_len(res.records[0]["text"])
        return res

    lines, res.footnotes = split_footnotes(clean.lines)

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

    struct_lines: set[int] = set()
    divisions: dict[int, str] = {}
    if len(accepted) >= 2:
        res.numbers = [c[1] for c in accepted]
        res.gaps = sorted(set(range(1, res.numbers[-1] + 1)) - accepted_nums)
        first = accepted[0][0]
        starts = [c[0] for c in accepted]
        res.toc = toc_entries(lines, first) if row["type"] == "irr" else []
        # Walk lines, pulling Chapter/Rule headings out as context.
        heading_idx = set(starts) | {len(lines)}
        current = ""
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
                while not m.group(3) and j < len(lines) and j not in heading_idx \
                        and not STRUCT_RE.match(lines[j].text) \
                        and (lines[j].text.upper() == lines[j].text or j == i + 1) and len(lines[j].text) < 100:
                    title.append(lines[j].text)
                    struct_lines.add(j)
                    j += 1
                # A footnote marker on a heading is not part of its name.
                name = re.sub(r"(?<=[A-Za-z.])\d{1,2}$", "", " ".join(title))
                current = f"{m.group(1).title()} {m.group(2)}" + (f": {name}" if name else "")
                i = j
                continue
            i += 1
    else:
        res.fallback = True
        first, starts = _part_bounds(lines)
        res.possible_missed = []
        if not starts:
            starts = [first]

    if first and any(k not in struct_lines for k in range(first)):
        pre = [l for k, l in enumerate(lines[:first]) if k not in struct_lines]
        res.records.append(_span(_base(row, "preamble", "preamble", "Preamble", "", pre), 0, first))

    bounds = starts + [len(lines)]
    numbered = not res.fallback
    by_num = {c[0]: c for c in accepted}
    for n, start in enumerate(starts):
        end = bounds[n + 1]
        idx = [k for k in range(start, end) if k not in struct_lines]
        body = [lines[k] for k in idx]
        sig: list[int] = []
        extra: list[int] = []
        if n == len(starts) - 1:
            for t, l in enumerate(body):
                if t and TRAILER_RE.match(l.text):
                    tail = idx[t:]
                    idx = idx[:t]
                    body = [lines[k] for k in idx]
                    cut = next((q for q, k in enumerate(tail) if EXTRA_RE.match(lines[k].text)), len(tail))
                    sig, extra = tail[:cut], tail[cut:]
                    break
        if numbered:
            _, num, rest = by_num[start]
            title = _title(lines, rest, start)
            rec = _base(row, "section", str(num), title, divisions.get(start, ""), body)
            if len(title.split()) > MAX_TITLE_WORDS:
                res.problems.append(f"s.{num}: long title, check heading split: {title[:80]}")
        else:
            if _is_part_title(lines, start, first):
                title = lines[start].text.strip()
            else:
                title = next((lines[k].text.strip() for k in idx if lines[k].text.strip() == "Overview"), "Opening text")
            rec = _base(row, "part", re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40], title, "", body)
        res.records.append(_span(rec, start, idx[-1] + 1 if idx else start))
        if sig:
            res.records.append(_span(_base(row, "signature", "signature", "Signatures and closing", "",
                                           [lines[k] for k in sig]), sig[0], sig[-1] + 1))
        if extra:
            head = lines[extra[0]].text
            summary = head.startswith("Summary")
            title = "Summary" if summary else re.split(r"\s*[:–—-]\s*", head)[0].strip().title()
            label = SUMMARY_LABEL if summary else None
            kind = "summary" if summary else "annex"
            res.records.append(_span(_base(row, kind, kind, title, "", [lines[k] for k in extra], label=label),
                                     extra[0], extra[-1] + 1))

    # Footnotes become their own records, linked to the record holding their marker.
    spans = [r for r in res.records if "_span" in r]
    for note in res.footnotes:
        # A marker on a Rule or Chapter heading belongs to no section; link it to the first one under it.
        parent = next((r for r in spans if r["_span"][0] <= note.marker_index < r["_span"][1]), None) \
            or next((r for r in spans if r["_span"][0] > note.marker_index), None) or spans[-1]
        note_line = Line(note.page, "\n".join(note.lines))
        rec = _base(row, "footnote", str(note.number), f"Footnote {note.number}", "", [note_line], label=ANNOTATION_LABEL)
        rec.update(parent_kind=parent["kind"], parent_section=parent["section"], marker_found=note.marker_found,
                   citation=f"{parent['citation']}, footnote {note.number} ({ANNOTATION_LABEL})")
        if row["status"] == "draft":
            rec["draft_label"] = DRAFT_LABEL
        res.records.append(rec)
    for r in spans:
        del r["_span"]
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
    return [r for r in res.records if r["kind"] in ("section", "part")]


def _lost(res: DocResult) -> int:
    return res.clean.raw_chars - res.clean.stripped_chars - res.accounted_chars


def toc_differences(res: DocResult) -> tuple[list[str], list[str]]:
    """Compare the IRR's contents with its body. Returns (number differences, title differences).

    A contents title that is a prefix of the body title is a contents entry wrapped onto a second
    line, not a difference. The body wording is kept as the heading.
    """
    body = {int(r["section"]): r["title"] for r in _secs(res)}
    toc = dict(res.toc)
    numbers = [f"s.{n} only in table of contents" for n in sorted(set(toc) - set(body))]
    numbers += [f"s.{n} only in body" for n in sorted(set(body) - set(toc))]
    titles = [f"s.{n}: contents `{toc[n]}`, body (kept) `{body[n]}`" for n in sorted(set(toc) & set(body))
              if not _title_key(body[n]).startswith(_title_key(toc[n]))]
    return numbers, titles


def run_checks(results: list[DocResult], catalogue_rows: list[dict]) -> list[dict]:
    """One row per check per document: check, doc_id, result (PASS/FAIL/REVIEW/INFO), detail."""
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
        secs = _secs(res)
        if res.fallback:
            add("No numbered sections: titled-part fallback", doc,
                "FAIL" if row["type"] in LAW_TYPES else "INFO",
                f"{len(secs)} parts: " + "; ".join(r["title"] for r in secs))
        else:
            own = DOCUMENT_OWN_GAPS.get(doc, [])
            clean_seq = not res.duplicates and not res.out_of_sequence
            if res.gaps == own and own and clean_seq:
                add("Numbering: no gaps or duplicates", doc, "REVIEW",
                    f"the document's own numbering skips {own}; confirmed by reading the text")
            elif not res.gaps and clean_seq:
                add("Numbering: no gaps or duplicates", doc, "PASS", f"1-{res.numbers[-1]}")
            else:
                add("Numbering: no gaps or duplicates", doc, "FAIL",
                    f"gaps {res.gaps}; duplicates {res.duplicates}; out of sequence {res.out_of_sequence}")
            add("Possible missed headings", doc, "FAIL" if res.possible_missed else "PASS",
                "; ".join(res.possible_missed) or f"none ({res.xrefs_dismissed} cross-references dismissed)")
            if res.midline_mentions:
                # With no gap in the numbering, a mid-line match cannot be a lost heading.
                add("Heading-shaped text inside a line", doc, "REVIEW" if res.gaps else "INFO",
                    "; ".join(res.midline_mentions))

        if row["type"] in LAW_TYPES:
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

        if res.footnotes:
            nums = [n.number for n in res.footnotes]
            missing = sorted(set(range(1, nums[-1] + 1)) - set(nums))
            no_marker = [n.number for n in res.footnotes if not n.marker_found]
            add("Footnotes separated and linked", doc, "REVIEW" if missing or no_marker else "PASS",
                f"{len(nums)} footnotes, 1-{nums[-1]}; missing {missing or 'none'}; "
                f"no marker found {no_marker or 'none'}")

        if row["type"] == "irr":
            numbers, titles = toc_differences(res)
            add("Section numbers match own table of contents", doc, "FAIL" if numbers else "PASS",
                "; ".join(numbers) or f"{len(res.toc)} entries, all match")
            if titles:
                add("IRR title variants recorded", doc, "INFO",
                    f"{len(titles)} worded differently; body wording kept as heading: " + "; ".join(titles))
        if doc in STATED_SECTION_COUNT:
            stated = STATED_SECTION_COUNT[doc]
            add(f"Has {stated} sections", doc, "PASS" if len(secs) == stated else "FAIL",
                f"document has {len(secs)}; s.{secs[-2]['section']} {secs[-2]['title']}, "
                f"s.{secs[-1]['section']} {secs[-1]['title']}")

    for res in results:
        if rows[res.doc_id]["status"] == "draft":
            ok = bool(res.records) and all(
                (r["label"] == DRAFT_LABEL or r.get("draft_label") == DRAFT_LABEL)
                and r["status"] == "draft" and r["authority"] == "draft" for r in res.records)
            add(f'Labelled "{DRAFT_LABEL}"', res.doc_id, "PASS" if ok else "FAIL",
                f"{len(res.records)} of {len(res.records)} records" if ok else "unlabelled records found")
        elif any(DRAFT_LABEL in r["label"] for r in res.records):
            add("No draft label on non-draft text", res.doc_id, "FAIL", "draft label on non-draft document")
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
        "Generated by `python -m ph_privacy_guide.ingest.sectioner`. Covers all 28 documents.", "",
        f"**Checks: {tally['PASS']} pass, {tally['FAIL']} fail, {tally['REVIEW']} to review, "
        f"{tally['INFO']} for information.**", "",
        "## Failures and items to review", "",
        "| Result | Check | Document | Detail |", "|---|---|---|---|",
    ]
    md += [f"| {c['result']} | {c['check']} | {c['doc_id']} | {c['detail']} |"
           for c in checks if c["result"] in ("FAIL", "REVIEW")]
    md += ["", "## Summary", "",
           f"Long = over {LONG_WORDS} words, split at the chunking step.", "",
           "| Document | Method | Sections or parts | Gaps | Duplicates | Long | Footnotes | Other records | Lost chars |",
           "|---|---|---:|---|---:|---:|---:|---|---:|"]
    for res in results:
        secs = _secs(res)
        other = Counter(r["kind"] for r in res.records if r["kind"] not in ("section", "part", "footnote"))
        method = "whole" if not secs else ("parts" if res.fallback else "numbered")
        md.append(f"| {res.doc_id} | {method} | {len(secs) or 'one block'} | {', '.join(map(str, res.gaps)) or 'none'} | "
                  f"{len(res.duplicates)} | {sum(_words(r) > LONG_WORDS for r in secs)} | {len(res.footnotes)} | "
                  f"{', '.join(f'{k} {v}' for k, v in sorted(other.items()))} | {_lost(res)} |")
    md += ["", "## All checks", "", "| Result | Check | Document | Detail |", "|---|---|---|---|"]
    md += [f"| {c['result']} | {c['check']} | {c['doc_id']} | {c['detail']} |" for c in checks]
    md += ["", "## Per-document details", ""]
    for res in results:
        items = [f"problem: {p}" for p in res.problems]
        if res.clean.stripped_line_numbers:
            items.append("margin line numbers stripped")
        items += [f"rejected duplicate candidate: {d}" for d in res.duplicates]
        items += [f"rejected out-of-sequence candidate: {d}" for d in res.out_of_sequence]
        for r in res.records:
            if r["kind"] in ("signature", "annex", "summary"):
                items.append(f"{r['kind']}: {_words(r)} words, p{r['page_start']}-{r['page_end']}")
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
