"""Hybrid search: BM25 plus embeddings, reciprocal rank fusion, fixed result blocks, score-based confidence.

Steps, all set in config.py and none tuned on any questions:
1. Rank allowed chunks by BM25, and separately by embedding similarity.
2. Fuse: score = sum over rankings of weight / (RRF_K + rank), equal weights.
3. Main block: the top passages that are statutes, rules or guidance. Drafts and the 16-03 Summary never
   enter it.
4. Side blocks: the best draft passage and the best Summary passage, at most SIDE_BLOCK_MAX each, only if
   the fused score reaches that of the last passage shown in the main block (the same relevance bar).
5. Confidence from the top fused score, margin, BM25/embedding agreement, top cosine and term overlap.
   "Not sure" if it falls below NOT_SURE_CONFIDENCE_THRESHOLD. While that is None, nothing is withheld.

`hits` and `side` are kept even when `not_sure` is true, so evaluation can measure them. Display code
must show no passage when `not_sure` is true.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import numpy as np

from ph_privacy_guide.config import (BLOCK_MAIN, BLOCK_PENDING, BLOCK_SUMMARY, EMBEDDING_THREADS, INCLUDE_DRAFT_ANNEX,
                                     MAIN_RESULTS, NOT_SURE_CONFIDENCE_THRESHOLD, RRF_K, RRF_WEIGHT_BM25,
                                     RRF_WEIGHT_EMBEDDING, SIDE_BLOCK_MAX)
from ph_privacy_guide.index import bm25
from ph_privacy_guide.retrieve.confidence import combine, compute_features, is_not_sure


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
    side: list[tuple[str, Hit]] = field(default_factory=list)
    confidence: float = 0.0
    features: dict = field(default_factory=dict)
    calibrated: bool = False
    timing: dict = field(default_factory=dict)


def fuse(rankings: list[tuple[list[int], float]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion over rankings of (ids best first, weight). Ranks start at 1."""
    scores: dict[int, float] = {}
    for ids, weight in rankings:
        for rank, i in enumerate(ids, 1):
            scores[i] = scores.get(i, 0.0) + weight / (k + rank)
    return scores


def select_side(ranked: list[int], score: dict[int, float], block_of, bar: float | None) -> list[tuple[str, int]]:
    """Best passages for each side block that reach the bar. `ranked` is best first, across all blocks."""
    if bar is None:
        return []
    out: list[tuple[str, int]] = []
    for block in (BLOCK_PENDING, BLOCK_SUMMARY):
        members = [i for i in ranked if block_of(i) == block and score[i] >= bar]
        out += [(block, i) for i in members[:SIDE_BLOCK_MAX]]
    return out


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

    def _hit(self, i: int, score: float, terms: list[str]) -> Hit:
        chunk = self.index_chunks[i]
        found = set(bm25.tokenize(chunk["index_text"]))
        return Hit(chunk, score, [t for t in terms if t in found])

    def search(self, query: str, k: int = MAIN_RESULTS, include_draft_annex: bool = INCLUDE_DRAFT_ANNEX) -> SearchResult:
        calibrated = NOT_SURE_CONFIDENCE_THRESHOLD is not None
        if not query.strip():
            return SearchResult([], [], True, "the search is empty", calibrated=calibrated)
        terms = list(dict.fromkeys(bm25.tokenize(query)))
        allowed = np.array([self._allowed(c, include_draft_annex) for c in self.index_chunks])
        block_of = lambda i: self.index_chunks[i]["block"]

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
        ranked = sorted(fused, key=lambda i: (-fused[i], i))
        main = [i for i in ranked if block_of(i) == BLOCK_MAIN]
        hits = [self._hit(i, fused[i], terms) for i in main[:k]]
        # The bar is always the last passage a reader sees in the main block, whatever k was asked for.
        shown = main[:MAIN_RESULTS]
        side = [(block, self._hit(i, fused[i], terms))
                for block, i in select_side(ranked, fused, block_of, fused[shown[-1]] if shown else None)]

        bm25_main = [i for i in bm25_ids if block_of(i) == BLOCK_MAIN]
        vector_main = [i for i in vector_ids if block_of(i) == BLOCK_MAIN]
        coverage = max((len(h.matched) for h in hits), default=0) / len(terms) if terms else 0.0
        features = compute_features([fused[i] for i in main[:2]], bm25_main, vector_main,
                                    float(similarity[vector_main[0]]) if vector_main else 0.0, coverage)
        confidence = combine(features)
        t4 = time.perf_counter()
        timing = {"bm25": t1 - t0, "encode": t2 - t1, "vector_search": t3 - t2, "fusion": t4 - t3, "total": t4 - t0}

        not_sure = is_not_sure(confidence, NOT_SURE_CONFIDENCE_THRESHOLD)
        reason = "confidence in these results is too low" if not_sure else ""
        return SearchResult(terms, hits, not_sure, reason, side, confidence, features, calibrated, timing)
