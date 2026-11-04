"""Score-based confidence for "not sure". Every feature runs from 0 to 1, higher meaning more confident.

Features:
  top_fused      top fused score, as a share of the highest score possible (ranked first by both methods)
  margin         gap between the first and second results, as a share of the first
  agreement      1 if BM25 and embeddings pick the same top chunk, otherwise the overlap of their top 5
  top_cosine     cosine similarity of the query and the closest passage
  term_coverage  share of search terms in the best passage; one feature only, never a gate by itself

The weights are equal defaults and the threshold is None until the dev set exists. With no threshold
nothing is ever withheld, and the display says that "not sure" is not active.
"""
from __future__ import annotations

from ph_privacy_guide.config import CONFIDENCE_WEIGHTS, RRF_K, RRF_WEIGHT_BM25, RRF_WEIGHT_EMBEDDING

AGREEMENT_DEPTH = 5


def compute_features(fused: list[float], bm25_ids: list[int], vector_ids: list[int], top_cosine: float,
                     term_coverage: float) -> dict[str, float]:
    """`fused` holds scores best first. The id lists are each method's ranking, best first."""
    best_possible = (RRF_WEIGHT_BM25 + RRF_WEIGHT_EMBEDDING) / (RRF_K + 1)
    top = fused[0] if fused else 0.0
    second = fused[1] if len(fused) > 1 else 0.0
    if bm25_ids and vector_ids and bm25_ids[0] == vector_ids[0]:
        agreement = 1.0
    else:
        agreement = len(set(bm25_ids[:AGREEMENT_DEPTH]) & set(vector_ids[:AGREEMENT_DEPTH])) / AGREEMENT_DEPTH
    return {
        "top_fused": min(1.0, top / best_possible),
        "margin": (top - second) / top if top else 0.0,
        "agreement": agreement,
        "top_cosine": max(0.0, min(1.0, top_cosine)),
        "term_coverage": term_coverage,
    }


def combine(features: dict[str, float], weights: dict[str, float] | None = None) -> float:
    weights = CONFIDENCE_WEIGHTS if weights is None else weights
    return sum(weights[k] * features[k] for k in weights) / sum(weights.values())


def is_not_sure(confidence: float, threshold: float | None) -> bool:
    return threshold is not None and confidence < threshold
