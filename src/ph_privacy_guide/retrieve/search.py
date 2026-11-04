"""Hybrid search: BM25 plus embeddings, reciprocal rank fusion, fixed tiers, and the "not sure" rule.

Steps, all set in config.py and none tuned on any questions:
1. Rank allowed chunks by BM25, and separately by embedding similarity.
2. Fuse: score = sum over rankings of weight / (RRF_K + rank), equal weights.
3. Take the top k by fused score, then order those by rank tier (rules and guidance, then the 16-03
   Summary, then the draft). A draft can be shown, but never above a rule or guidance passage.
4. "Not sure" if the best passage has under NOT_SURE_MIN_TERM_COVERAGE of the search terms.

`hits` keeps the ranking even when `not_sure` is true, so evaluation can measure both. Display code
must show no passage when `not_sure` is true.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import numpy as np

from ph_privacy_guide.config import (EMBEDDING_THREADS, INCLUDE_DRAFT_ANNEX, NOT_SURE_MIN_TERM_COVERAGE,
                                     RESULTS_SHOWN, RRF_K, RRF_WEIGHT_BM25, RRF_WEIGHT_EMBEDDING)
from ph_privacy_guide.index import bm25


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
    timing: dict = field(default_factory=dict)


def fuse(rankings: list[tuple[list[int], float]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion over rankings of (ids best first, weight). Ranks start at 1."""
    scores: dict[int, float] = {}
    for ids, weight in rankings:
        for rank, i in enumerate(ids, 1):
            scores[i] = scores.get(i, 0.0) + weight / (k + rank)
    return scores


class Searcher:
    def __init__(self, threads: int = EMBEDDING_THREADS) -> None:
        from ph_privacy_guide.index import embed

        self.index = bm25.load()
        with open(bm25.CHUNKS) as f:
            self.chunks = {c["chunk_id"]: c for c in map(json.loads, f)}
        self.vectors, vector_ids = embed.load_vectors()
        if vector_ids != self.index["chunk_ids"]:
            raise RuntimeError("the embedding and BM25 indexes list different chunks; rebuild both")
        self.embedder = embed.Embedder(threads=threads)
        self.index_chunks = [self.chunks[i] for i in self.index["chunk_ids"]]

    def _allowed(self, chunk: dict, include_draft_annex: bool) -> bool:
        return chunk["searchable"] or (include_draft_annex and chunk["switch"] == "draft_annex")

    def search(self, query: str, k: int = RESULTS_SHOWN, include_draft_annex: bool = INCLUDE_DRAFT_ANNEX) -> SearchResult:
        if not query.strip():
            return SearchResult([], [], True, "the search is empty")
        terms = list(dict.fromkeys(bm25.tokenize(query)))
        allowed = np.array([self._allowed(c, include_draft_annex) for c in self.index_chunks])

        t0 = time.perf_counter()
        keyword = bm25.score(self.index, terms)
        bm25_ids = sorted((i for i in keyword if allowed[i]), key=lambda i: (-keyword[i], i))
        t1 = time.perf_counter()
        query_vector = self.embedder.encode_query(query)
        t2 = time.perf_counter()
        similarity = self.vectors @ query_vector
        vector_ids = [int(i) for i in np.argsort(-similarity, kind="stable") if allowed[i]]
        t3 = time.perf_counter()
        fused = fuse([(bm25_ids, RRF_WEIGHT_BM25), (vector_ids, RRF_WEIGHT_EMBEDDING)])
        top = sorted(fused, key=lambda i: (-fused[i], i))[:k]
        top.sort(key=lambda i: self.index_chunks[i]["rank_tier"])  # stable: keeps relevance order in a tier
        hits = []
        for i in top:
            chunk = self.index_chunks[i]
            found = set(bm25.tokenize(chunk["index_text"]))
            hits.append(Hit(chunk, fused[i], [t for t in terms if t in found]))
        t4 = time.perf_counter()
        timing = {"bm25": t1 - t0, "encode": t2 - t1, "vector_search": t3 - t2, "fusion": t4 - t3, "total": t4 - t0}

        if not terms:
            return SearchResult(terms, hits, True, "the search has no usable terms", timing)
        best = max((len(h.matched) for h in hits), default=0) / len(terms)
        if best == 0:
            return SearchResult(terms, hits, True, "no passage shown contains any of the search terms", timing)
        if best < NOT_SURE_MIN_TERM_COVERAGE:
            return SearchResult(terms, hits, True,
                                f"the closest passage contains only {best:.0%} of the search terms", timing)
        return SearchResult(terms, hits, False, "", timing)
