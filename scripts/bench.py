#!/usr/bin/env python3
"""Record size, memory and CPU latency. Writes results/bench/<date>_<commit>.json.

Usage: .venv/bin/python scripts/bench.py

Each thread setting runs in a fresh process, so cold start and peak memory are real. The queries are
section headings taken from the corpus by code, with a fixed seed: they measure speed only, and are
never used to judge relevance or to tune anything.
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time

from ph_privacy_guide.config import EMBEDDING_MODEL_DIR, EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_REVISION, PROCESSED, ROOT

N_QUERIES = 200
WARM_UP = 5
SEED = 0
THREAD_SETTINGS = (0, 2)  # 0 = onnxruntime's default for this machine; 2 = a rough stand-in for a low-end laptop


def rule_queries() -> list[str]:
    with open(PROCESSED / "chunks.jsonl") as f:
        titles = sorted({c["title"] for c in map(json.loads, f) if c["kind"] in ("section", "part")})
    rng = random.Random(SEED)
    return [rng.choice(titles) for _ in range(WARM_UP + N_QUERIES)]


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def worker(threads: int) -> None:
    from ph_privacy_guide.offline import enforce_offline

    enforce_offline()
    start = time.perf_counter()
    from ph_privacy_guide.retrieve.search import Searcher

    searcher = Searcher(threads=threads)
    cold = time.perf_counter() - start
    from ph_privacy_guide.sysinfo import peak_rss_bytes

    after_load = peak_rss_bytes()
    queries = rule_queries()
    start = time.perf_counter()
    searcher.search(queries[0])
    first_query = time.perf_counter() - start
    for q in queries[1:WARM_UP]:
        searcher.search(q)
    timings = [searcher.search(q).timing for q in queries[WARM_UP:]]
    summary = {}
    for key in ("bm25", "encode", "vector_search", "fusion", "total"):
        values = [t[key] * 1000 for t in timings]
        summary[key] = {"p50_ms": round(statistics.median(values), 2), "p95_ms": round(percentile(values, 0.95), 2),
                        "max_ms": round(max(values), 2)}
    print(json.dumps({"threads_setting": threads, "cold_start_seconds": round(cold, 3),
                      "first_query_seconds": round(first_query, 3), "peak_rss_after_load_bytes": after_load,
                      "peak_rss_after_queries_bytes": peak_rss_bytes(), "queries": len(timings), "latency": summary}))


def tree_bytes(path) -> int:
    total = 0
    for base, _, names in os.walk(path):
        for name in names:
            full = os.path.join(base, name)
            if not os.path.islink(full):
                total += os.path.getsize(full)
    return total


def machine() -> dict:
    def sysctl(key: str) -> str:
        return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True).stdout.strip()

    import numpy
    import onnxruntime
    import tokenizers

    return {"cpu": sysctl("machdep.cpu.brand_string") or platform.processor(), "logical_cores": os.cpu_count(),
            "ram_bytes": int(sysctl("hw.memsize") or 0), "os": platform.platform(), "python": platform.python_version(),
            "onnxruntime": onnxruntime.__version__, "tokenizers": tokenizers.__version__, "numpy": numpy.__version__}


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(int(sys.argv[2]))
        return
    runs = []
    for threads in THREAD_SETTINGS:
        out = subprocess.run([sys.executable, __file__, "--worker", str(threads)], capture_output=True, text=True, check=True)
        runs.append(json.loads(out.stdout))
    indexes = ROOT / "indexes"
    meta = json.loads((indexes / "embeddings.json").read_text())
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    result = {
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "commit": commit,
        "machine": machine(),
        "model": {"name": EMBEDDING_MODEL_NAME, "revision": EMBEDDING_MODEL_REVISION,
                  "model_dir_bytes": tree_bytes(EMBEDDING_MODEL_DIR),
                  "model_onnx_bytes": (EMBEDDING_MODEL_DIR / "onnx" / "model.onnx").stat().st_size},
        "sizes": {"bm25_index_bytes": (indexes / "bm25.json").stat().st_size,
                  "embedding_matrix_bytes": (indexes / "embeddings.npy").stat().st_size,
                  "embedding_metadata_bytes": (indexes / "embeddings.json").stat().st_size,
                  "chunks_jsonl_bytes": (PROCESSED / "chunks.jsonl").stat().st_size,
                  "venv_bytes": tree_bytes(ROOT / ".venv")},
        "index_build": {k: meta[k] for k in ("chunks", "dimensions", "tokens_max", "truncated_chunks", "model_load_seconds",
                                             "embedding_seconds", "chunks_per_second", "build_peak_rss_bytes")},
        "runs": runs,
    }
    out_dir = ROOT / "results" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{datetime.date.today().isoformat()}_{commit}.json"
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nSaved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
