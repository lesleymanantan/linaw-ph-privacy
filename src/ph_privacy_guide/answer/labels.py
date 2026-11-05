"""Interface labels and result card wording. Labels come from data/i18n/labels.csv.

Only the interface is translated. An empty fil cell falls back to English, and passage text is never
translated. Stored chunks are never changed: everything here works on a copy for display.
"""
from __future__ import annotations

import csv
import html
import re
from functools import lru_cache

from ph_privacy_guide.answer.warnings import marked_superseded, status_text
from ph_privacy_guide.config import LABELS_CSV, LISTED_LABEL

LANGUAGES = ("en", "fil")
DEFAULT_LANGUAGE = "en"
SECTION_RE = re.compile(r", s\.(?=\d)")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


@lru_cache(maxsize=1)
def load_labels() -> dict[str, dict[str, str]]:
    with open(LABELS_CSV, newline="", encoding="utf-8") as f:
        return {row["key"]: row for row in csv.DictReader(f)}


def label(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    row = load_labels()[key]
    return row.get(lang) or row["en"]


def has_translation(lang: str) -> bool:
    return any(row.get(lang) for row in load_labels().values())


def type_text(chunk: dict, lang: str = DEFAULT_LANGUAGE) -> str:
    key = "summary" if chunk.get("kind") == "summary" else chunk["authority"]
    if key == "rule" and marked_superseded(chunk):
        key = "rule_superseded"
    return label(f"type.{key}", lang) if f"type.{key}" in load_labels() else chunk["authority"]


def status_display(chunk: dict, lang: str = DEFAULT_LANGUAGE) -> str:
    """The on-screen status. The catalogue's label stays as it is; only the plain listed wording is reworded here."""
    english = status_text(chunk)
    if english == LISTED_LABEL:
        return label("status.listed", lang)
    for key, row in load_labels().items():
        if key.startswith("status.") and row["en"] == english:
            return label(key, lang)
    return english


def _issued(date: str, lang: str) -> str:
    m = DATE_RE.match(date)
    return f"{int(m.group(3))} {label('month.' + m.group(2), lang)} {m.group(1)}" if m else date


def source_text(chunk: dict, lang: str = DEFAULT_LANGUAGE) -> str:
    """Source: NPC Circular 2022-04, section 10, pages 7-8 (issued 5 Dec 2022)"""
    citation = SECTION_RE.sub(f", {label('source.section', lang)} ", chunk["citation"])
    start, end = chunk["page_start"], chunk["page_end"]
    pages = f"{label('source.page', lang)} {start}" if start == end else f"{label('source.pages', lang)} {start}-{end}"
    issued = f" ({label('source.issued', lang)} {_issued(chunk['date_issued'], lang)})" if chunk.get("date_issued") else ""
    return f"{label('source.label', lang)}: {citation}, {pages}{issued}"


@lru_cache(maxsize=1)
def _abbreviation_re() -> re.Pattern:
    names = sorted((k.split(".", 1)[1] for k in load_labels() if k.startswith("abbr.")), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(names) + r")(s?)\b")


def abbreviate(escaped_text: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """Wrap known abbreviations in <abbr>. Takes text that is already HTML-escaped, and is for display only."""
    def wrap(m: re.Match) -> str:
        return f'<abbr title="{html.escape(label("abbr." + m.group(1), lang), quote=True)}">{m.group(0)}</abbr>'
    return _abbreviation_re().sub(wrap, escaped_text)
