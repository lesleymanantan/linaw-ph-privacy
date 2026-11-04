"""Keyword search over chunks: filtering, ranking tiers and the provisional "not sure" rule.

The "not sure" rule is a placeholder until a threshold can be set on human-written dev questions:
say "not sure" if nothing matches, or the best passage contains under half the search terms.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ph_privacy_guide.config import INCLUDE_DRAFT_ANNEX
from ph_privacy_guide.index import bm25

MIN_TERM_COVERAGE = 0.5


@dataclass
class Hit:
    chunk: dict
    score: float
    matched: list[str]


@dataclass
class SearchResult:
    query_terms: list[str]
    hits: list[Hit]
    not_sure: bool
    reason: str


class Searcher:
    def __init__(self) -> None:
        self.index = bm25.load()
        with open(bm25.CHUNKS) as f:
            self.chunks = {c["chunk_id"]: c for c in map(json.loads, f)}

    def _allowed(self, chunk: dict, include_draft_annex: bool) -> bool:
        return chunk["searchable"] or (include_draft_annex and chunk["switch"] == "draft_annex")

    def search(self, query: str, k: int = 5, include_draft_annex: bool = INCLUDE_DRAFT_ANNEX) -> SearchResult:
        terms = list(dict.fromkeys(bm25.tokenize(query)))
        if not terms:
            return SearchResult(terms, [], True, "the search has no usable terms")
        ranked = []
        for i, value in bm25.score(self.index, terms).items():
            chunk = self.chunks[self.index["chunk_ids"][i]]
            if self._allowed(chunk, include_draft_annex):
                ranked.append((chunk["rank_tier"], -value, chunk["chunk_id"], chunk))
        ranked.sort(key=lambda r: r[:3])
        hits = []
        for _, neg, _, chunk in ranked[:k]:
            found = set(bm25.tokenize(chunk["index_text"]))
            hits.append(Hit(chunk, -neg, [t for t in terms if t in found]))
        if not hits:
            return SearchResult(terms, [], True, "no passage contains any of the search terms")
        best = max(len(h.matched) for h in hits) / len(terms)
        if best < MIN_TERM_COVERAGE:
            return SearchResult(terms, [], True, f"the closest passage contains under half of the search terms ({best:.0%})")
        return SearchResult(terms, hits, False, "")
