"""Format search results for the terminal. Passage text is printed exactly as stored."""
from __future__ import annotations

from ph_privacy_guide.answer.warnings import STATUS_WORDS
from ph_privacy_guide.config import ANNOTATION_LABEL, BLOCK_HEADINGS, CONTACT_URL
from ph_privacy_guide.retrieve.search import SearchResult

RULE = "-" * 78
LIMIT_NOTE = "Not legal advice. Read the full instrument and check privacy.gov.ph for current versions."
UNCALIBRATED_NOTE = ('"Not sure" is not active yet: its threshold has not been set. '
                     "These passages may not answer your question.")


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
    lines += [f"    Note: {n}" for n in c.get("notes", [])]
    lines += [RULE, c["text"], RULE]
    for note in c["annotations"]:
        lines += [f"{ANNOTATION_LABEL} {note['number']} (not the provision's text):", note["text"], RULE]
    return "\n".join(lines)


def format_result(query: str, result: SearchResult) -> str:
    head = f'Search: "{query}"'
    if result.not_sure:
        return (f"{head}\n\nNot sure. {result.reason.capitalize()}. No passage is shown.\n"
                f"You can ask the National Privacy Commission: {CONTACT_URL}\n\n{LIMIT_NOTE}")
    parts = [format_hit(i, h) for i, h in enumerate(result.hits, 1)]
    next_rank = len(result.hits) + 1
    for block, hit in result.side:
        heading = BLOCK_HEADINGS[block]
        parts.append(f"=== {heading} ===\n{format_hit(next_rank, hit)}")
        next_rank += 1
    note = "" if result.calibrated else f"{UNCALIBRATED_NOTE}\n\n"
    return f"{head}\n\n{note}" + "\n\n".join(parts) + f"\n\n{LIMIT_NOTE}"
