"""Warnings shown with a passage. Computed once at chunking and stored on the chunk."""
from __future__ import annotations

import re

from ph_privacy_guide.config import DRAFT_LABEL, REPEALED_FOOTNOTE_WARNINGS, SUMMARY_LABEL, TOOLKIT_LABEL

STATUS_WORDS = {"in_force": "in force", "repealed": "repealed", "amended": "amended",
                "draft": DRAFT_LABEL, "unverified": "not verified"}


def annotation_warnings(row_type: str, footnotes: list[dict], cites: dict[str, str]) -> list[str]:
    """IRR chunks whose linked footnotes cite a repealed circular listed in the config."""
    if row_type != "irr":
        return []
    out = []
    for note in footnotes:
        flat = re.sub(r"\s+", " ", note["text"])
        for pattern, (repealed, replacement) in REPEALED_FOOTNOTE_WARNINGS.items():
            if re.search(pattern, flat):
                out.append(f"NPC annotation {note['number']} cites {repealed}, which is repealed. "
                           f"See {cites[replacement]}.")
    return out


def status_warnings(rec: dict, cites: dict[str, str]) -> list[str]:
    out = []
    if rec["status"] == "draft":
        out.append(f"DRAFT: {DRAFT_LABEL}. This text is not law.")
    if rec["status"] == "repealed":
        target = cites.get(rec["replaced_by"], rec["replaced_by"])
        out.append(f"REPEALED: replaced by {target}.")
    if rec["supplemented_by"]:
        out.append(f"Supplemented by {cites.get(rec['supplemented_by'], rec['supplemented_by'])}.")
    if rec["label"] == SUMMARY_LABEL:
        out.append(f"{SUMMARY_LABEL}.")
    if rec["label"] == TOOLKIT_LABEL:
        out.append(f"{TOOLKIT_LABEL.capitalize()}.")
    return out
