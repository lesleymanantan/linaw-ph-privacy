"""Embeddings with the approved local model, run on the CPU through onnxruntime.

Usage: python -m ph_privacy_guide.index.embed    # build indexes/embeddings.npy for the BM25 chunk list

Loads only from models/. Never downloads: scripts/download_model.py is the one dev-only download.
"""
from __future__ import annotations

import json
import time

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from ph_privacy_guide.config import (EMBEDDING_MAX_TOKENS, EMBEDDING_MODEL_DIR, EMBEDDING_MODEL_REVISION,
                                     EMBEDDING_PASSAGE_PREFIX, EMBEDDING_QUERY_PREFIX, EMBEDDING_THREADS, ROOT)
from ph_privacy_guide.index import bm25
from ph_privacy_guide.sysinfo import peak_rss_bytes

VECTORS = ROOT / "indexes" / "embeddings.npy"
VECTORS_META = ROOT / "indexes" / "embeddings.json"
BATCH_SIZE = 16


class Embedder:
    def __init__(self, threads: int = EMBEDDING_THREADS) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(EMBEDDING_MODEL_DIR / "onnx" / "model.onnx"), options,
                                            providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(EMBEDDING_MODEL_DIR / "onnx" / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=EMBEDDING_MAX_TOKENS)
        self.tokenizer.enable_padding()

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, feed)[0]
        # Mean pooling over real tokens, then unit length, as the model card specifies.
        weights = mask[..., None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode_batch([EMBEDDING_QUERY_PREFIX + text])[0].astype(np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        # Similar lengths together, so batches pad less.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros((len(texts), 0), dtype=np.float32)
        for start in range(0, len(order), BATCH_SIZE):
            idx = order[start:start + BATCH_SIZE]
            vectors = self._encode_batch([EMBEDDING_PASSAGE_PREFIX + texts[i] for i in idx])
            if out.shape[1] == 0:
                out = np.zeros((len(texts), vectors.shape[1]), dtype=np.float32)
            out[idx] = vectors
        return out


def build() -> dict:
    index = bm25.load()
    with open(bm25.CHUNKS) as f:
        chunks = {c["chunk_id"]: c for c in map(json.loads, f)}
    texts = [chunks[i]["index_text"] for i in index["chunk_ids"]]
    start = time.perf_counter()
    embedder = Embedder()
    load_seconds = time.perf_counter() - start
    counter = Tokenizer.from_file(str(EMBEDDING_MODEL_DIR / "onnx" / "tokenizer.json"))
    lengths = [len(counter.encode(EMBEDDING_PASSAGE_PREFIX + t).ids) for t in texts]
    truncated = [cid for cid, n in zip(index["chunk_ids"], lengths) if n > EMBEDDING_MAX_TOKENS]
    start = time.perf_counter()
    vectors = embedder.encode_passages(texts)
    seconds = time.perf_counter() - start
    np.save(VECTORS, vectors)
    meta = {
        "chunks_sha256": index["chunks_sha256"], "chunk_ids": index["chunk_ids"],
        "model_revision": EMBEDDING_MODEL_REVISION, "dimensions": int(vectors.shape[1]),
        "chunks": len(texts), "tokens_max": max(lengths), "truncated_chunks": truncated,
        "model_load_seconds": round(load_seconds, 3), "embedding_seconds": round(seconds, 3),
        "chunks_per_second": round(len(texts) / seconds, 2), "build_peak_rss_bytes": peak_rss_bytes(),
    }
    VECTORS_META.write_text(json.dumps(meta))
    return meta


def load_vectors() -> tuple[np.ndarray, list[str]]:
    meta = json.loads(VECTORS_META.read_text())
    index_hash = bm25.chunks_hash()
    if meta["chunks_sha256"] != index_hash:
        raise RuntimeError("indexes/embeddings.npy is older than chunks.jsonl; rebuild it")
    if meta["model_revision"] != EMBEDDING_MODEL_REVISION:
        raise RuntimeError("indexes/embeddings.npy was built with another model revision; rebuild it")
    return np.load(VECTORS), meta["chunk_ids"]


def main() -> None:
    meta = build()
    print(json.dumps({k: v for k, v in meta.items() if k != "chunk_ids"}, indent=2))


if __name__ == "__main__":
    main()
