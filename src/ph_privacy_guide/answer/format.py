"""Format search results for the terminal. Passage text is printed exactly as stored."""
from __future__ import annotations

from ph_privacy_guide.answer.warnings import STATUS_WORDS
from ph_privacy_guide.config import ANNOTATION_LABEL
from ph_privacy_guide.retrieve.search import SearchResult

RULE = "-" * 78
LIMIT_NOTE = "Not legal advice. Read the full instrument and check privacy.gov.ph for current versions."


def format_hit(rank: int, hit) -> str:
    c = hit.chunk
    pages = f"p.{c['page_start']}" if c["page_start"] == c["page_end"] else f"pp.{c['page_start']}-{c['page_end']}"
    meta = [f"Authority: {c['authority']}", f"Status: {STATUS_WORDS[c['status']]}"]
    if c["date_issued"]:
        meta.append(f"Issued: {c['date_issued']}")
    meta.append(pages)
    lines = [f"[{rank}] {c['citation']}", "    " + " | ".join(meta)]
    if c["title"] and c["kind"] in ("section", "part"):
        lines.append(f"    Heading: {c['title']}")
    lines += [f"    WARNING: {w}" for w in c["warnings"]]
    lines += [RULE, c["text"], RULE]
    for note in c["annotations"]:
        lines += [f"{ANNOTATION_LABEL} {note['number']} (not the provision's text):", note["text"], RULE]
    return "\n".join(lines)


def format_result(query: str, result: SearchResult) -> str:
    head = f'Search: "{query}"'
    if result.not_sure:
        return f"{head}\n\nNot sure. {result.reason.capitalize()}. No passage is shown.\n\n{LIMIT_NOTE}"
    body = "\n\n".join(format_hit(i, h) for i, h in enumerate(result.hits, 1))
    return f"{head}\n\n{body}\n\n{LIMIT_NOTE}"
