"""A small Okapi BM25 keyword index, using only the standard library.

Usage: python -m ph_privacy_guide.index.bm25      # build indexes/bm25.json from chunks.jsonl

Preambles, signature blocks and footnotes are not indexed. The draft's Annex A is indexed but
filtered out at search time unless the switch is on. No stemming yet.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter

from ph_privacy_guide.config import PROCESSED, ROOT, SEARCHABLE_KINDS

INDEX = ROOT / "indexes" / "bm25.json"
CHUNKS = PROCESSED / "chunks.jsonl"
K1, B = 1.2, 0.75
TOKEN_RE = re.compile(r"[a-z0-9ñ]+")
STOPWORDS = frozenset(
    "a an and are as at be been but by can do does for from had has have how i if in into is it its may me my "
    "no not of on or our shall should so such than that the their them then there these they this to under "
    "was we were what when where which who whom why will with would you your".split())


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def _chunks_hash() -> str:
    return hashlib.sha256(CHUNKS.read_bytes()).hexdigest()


def build() -> dict:
    with open(CHUNKS) as f:
        chunks = [json.loads(line) for line in f]
    docs = [c for c in chunks if c["kind"] in SEARCHABLE_KINDS and c["index_text"]]
    postings: dict[str, list[list[int]]] = {}
    lengths = []
    for i, c in enumerate(docs):
        tf = Counter(tokenize(c["index_text"]))
        lengths.append(sum(tf.values()))
        for term, n in tf.items():
            postings.setdefault(term, []).append([i, n])
    index = {"chunks_sha256": _chunks_hash(), "k1": K1, "b": B, "chunk_ids": [c["chunk_id"] for c in docs],
             "lengths": lengths, "avg_length": sum(lengths) / len(lengths), "postings": postings}
    INDEX.parent.mkdir(exist_ok=True)
    INDEX.write_text(json.dumps(index))
    return index


def load() -> dict:
    index = json.loads(INDEX.read_text())
    if index["chunks_sha256"] != _chunks_hash():
        raise RuntimeError("indexes/bm25.json is older than chunks.jsonl; rebuild it")
    return index


def score(index: dict, query_terms: list[str]) -> dict[int, float]:
    n, avg, k1, b = len(index["lengths"]), index["avg_length"], index["k1"], index["b"]
    scores: dict[int, float] = {}
    for term in set(query_terms):
        posting = index["postings"].get(term, [])
        if not posting:
            continue
        idf = math.log(1 + (n - len(posting) + 0.5) / (len(posting) + 0.5))
        for i, tf in posting:
            norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * index["lengths"][i] / avg))
            scores[i] = scores.get(i, 0.0) + idf * norm
    return scores


def main() -> None:
    index = build()
    print(f"{len(index['chunk_ids'])} chunks indexed, {len(index['postings'])} terms, "
          f"{INDEX.stat().st_size / 1_000_000:.1f} MB at {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
