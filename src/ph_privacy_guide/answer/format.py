"""Format search results for the terminal. Passage text is printed exactly as stored."""
from __future__ import annotations

from ph_privacy_guide import catalogue
from ph_privacy_guide.answer.labels import label, source_text, status_display, type_text
from ph_privacy_guide.config import BLOCK_PENDING, BLOCK_SUMMARY, CONTACT_URL
from ph_privacy_guide.retrieve.search import SearchResult

RULE = "-" * 78
BLOCK_KEYS = {BLOCK_PENDING: "block.pending", BLOCK_SUMMARY: "block.summary"}


def format_hit(rank: int, hit) -> str:
    c = hit.chunk
    lines = [f"[{rank}] {c['citation']}",
             f"    {label('type.label')}: {type_text(c)} | {label('status.label')}: {status_display(c)}",
             f"    {source_text(c)}"]
    link = catalogue.official_url(catalogue.source_urls().get(c.get("doc_id"), ""), c["page_start"])
    if link:
        lines.append(f"    {label('link.official')}: {link}")
    if c["title"] and c["kind"] in ("section", "part"):
        lines.append(f"    {label('card.heading')}: {c['title']}")
    lines += [f"    {label('card.warning')}: {w}" for w in c["warnings"]]
    lines += [f"    {label('card.note')}: {n}" for n in c.get("notes", [])]
    lines += [RULE, c["text"], RULE]
    for note in c["annotations"]:
        lines += [f"{label('annotation.label')} {note['number']} {label('annotation.not_text')}:", note["text"], RULE]
    return "\n".join(lines)


def format_result(query: str, result: SearchResult) -> str:
    head = f'Search: "{query}"'
    limit = label("page.limit_note")
    if result.not_sure:
        return (f"{head}\n\n{label('not_sure.heading')}. {result.reason.capitalize()}. {label('not_sure.no_passage')}\n"
                f"{label('not_sure.contact')} {CONTACT_URL}\n\n{limit}")
    parts = [format_hit(i, h) for i, h in enumerate(result.hits, 1)]
    next_rank = len(result.hits) + 1
    for block, hit in result.side:
        parts.append(f"=== {label(BLOCK_KEYS[block])} ===\n{format_hit(next_rank, hit)}")
        next_rank += 1
    note = "" if result.calibrated else f"{label('banner.threshold_off')}\n\n"
    return f"{head}\n\n{note}" + "\n\n".join(parts) + f"\n\n{label('results.english_note')}\n{limit}"
