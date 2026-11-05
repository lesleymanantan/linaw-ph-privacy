"""Warnings shown with a passage. Computed once at chunking and stored on the chunk."""
from __future__ import annotations

import re

from ph_privacy_guide.config import (ANNOTATION_SUPERSEDED, DOCUMENT_WARNINGS, DRAFT_LABEL, LISTED_LABEL, REPEALED_FOOTNOTE_WARNINGS, SECTION_WARNINGS,
                                     STATUS_LISTED, SUMMARY_LABEL, TEXT_ANNOTATION_WARNINGS, TOOLKIT_LABEL)

STATUS_WORDS = {"repealed": "repealed", "amended": "amended",
                "draft": DRAFT_LABEL, "unverified": "not verified", STATUS_LISTED: LISTED_LABEL}


def status_text(chunk: dict) -> str:
    """The on-screen status: the catalogue's label for that document."""
    return chunk.get("status_label") or STATUS_WORDS[chunk["status"]]


def annotation_warnings(row_type: str, footnotes: list[dict], cites: dict[str, str]) -> list[str]:
    """IRR chunks whose linked footnotes cite a repealed circular listed in the config."""
    if row_type != "irr":
        return []
    out = []
    for note in footnotes:
        flat = re.sub(r"\s+", " ", note["text"])
        for pattern, (repealed, replacement, basis) in REPEALED_FOOTNOTE_WARNINGS.items():
            if re.search(pattern, flat):
                out.append(f"NPC annotation {note['number']} cites {repealed}, which is repealed. "
                           f"See {cites[replacement]} ({basis}).")
    return out


def _annotations_on(chunk: dict) -> list[tuple[str, str, str, str]]:
    """The configured text annotations covering this chunk, as (doc_id and section label, effect, quote, target)."""
    if chunk.get("kind") != "section":
        return []
    return [(f"{doc_id} s.{section}", effect, quote, target)
            for (doc_id, section, prefix), (effect, quote, target) in TEXT_ANNOTATION_WARNINGS.items()
            if chunk.get("doc_id") == doc_id and chunk.get("section") == section and chunk.get("subsection", "").startswith(prefix)]


def marked_superseded(chunk: dict) -> bool:
    """True where an NPC annotation printed in the text marks this section as superseded."""
    return any(effect == ANNOTATION_SUPERSEDED for _, effect, _, _ in _annotations_on(chunk))


def text_annotation_warnings(chunk: dict, section_text: str, cites: dict[str, str]) -> list[str]:
    """Quote an annotation printed in the section, on the chunks it covers. Stops if the quote is not there."""
    out = []
    for where, effect, quote, target in _annotations_on(chunk):
        if quote not in re.sub(r"\s+", " ", section_text):
            raise ValueError(f"{where}: annotation not found in the text: {quote}")
        out.append(f'{effect}: the NPC annotation in this text reads "{quote}". See {cites[target]}.')
    return out


def status_warnings(rec: dict, cites: dict[str, str]) -> list[str]:
    out = []
    if rec["status"] == "draft":
        out.append(f"DRAFT: {DRAFT_LABEL}. This text is not law.")
    if rec["status"] == "repealed":
        target = cites.get(rec["replaced_by"], rec["replaced_by"])
        out.append(f"REPEALED: replaced by {target}.")
    if rec["clarified_by"]:
        out.append(f"{cites.get(rec['clarified_by'], rec['clarified_by'])} gives clarifications for requests under this circular.")
    if rec.get("doc_id") in DOCUMENT_WARNINGS:
        out.append(DOCUMENT_WARNINGS[rec["doc_id"]])
    if rec.get("kind") == "section" and (rec["doc_id"], rec["section"]) in SECTION_WARNINGS:
        out.append(SECTION_WARNINGS[(rec["doc_id"], rec["section"])])
    if rec["label"] == SUMMARY_LABEL:
        out.append(f"{SUMMARY_LABEL}.")
    if rec["label"] == TOOLKIT_LABEL:
        out.append(f"{TOOLKIT_LABEL.capitalize()}.")
    return out
