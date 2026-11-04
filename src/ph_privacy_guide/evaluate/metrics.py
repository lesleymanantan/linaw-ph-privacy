"""Evaluation metrics, and the gates that keep the test split apart from dev.

The dev command takes no file argument. The test split runs only through run_final, which requires
the explicit flag, a committed hash, unchanged committed files, and no earlier final run.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import random
import subprocess
from pathlib import Path

from ph_privacy_guide import config
from ph_privacy_guide.evaluate.questions import QUESTIONS_DIR, load_chunks, load_split, resolve_gold_ids, validate_set

RESULTS_DIR = config.ROOT / "results" / "eval"
GROUPS = ("all", "en", "fil", "taglish")
TOP_K = 5
BOOTSTRAP_ROUNDS = 1000
SWEEP_THRESHOLDS = [round(0.05 * i, 2) for i in range(21)]


def score_question(question: dict, gold_ids: set[str], result) -> dict:
    """gold_rank is the position in the main block's ranking. Side blocks are counted apart."""
    hit_ids = [h.chunk["chunk_id"] for h in result.hits]
    rank = next((i for i, cid in enumerate(hit_ids, 1) if cid in gold_ids), None)
    side_ids = [h.chunk["chunk_id"] for _, h in result.side]
    return {"id": question["id"], "language": question["language"], "answerable": question["answerable"],
            "not_sure": result.not_sure, "gold_rank": rank, "gold_in_side_block": bool(gold_ids & set(side_ids)),
            "top": hit_ids[:TOP_K], "side": side_ids, "confidence": result.confidence, "features": result.features}


def _rate(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _interval(values: list[float]) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(0)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(BOOTSTRAP_ROUNDS))
    return [round(means[int(0.025 * BOOTSTRAP_ROUNDS)], 4), round(means[int(0.975 * BOOTSTRAP_ROUNDS) - 1], 4)]


def summarise(scored: list[dict]) -> dict:
    answerable = [s for s in scored if s["answerable"]]
    unanswerable = [s for s in scored if not s["answerable"]]
    answered = [s for s in scored if not s["not_sure"]]
    out: dict = {"n": len(scored), "n_answerable": len(answerable), "n_unanswerable": len(unanswerable),
                 "n_answered": len(answered)}
    for k in (1, 3, 5):
        hits = [1.0 if s["gold_rank"] and s["gold_rank"] <= k else 0.0 for s in answerable]
        out[f"recall@{k}"] = _rate(hits)
        out[f"recall@{k}_ci95"] = _interval(hits)
    reciprocal = [1.0 / s["gold_rank"] if s["gold_rank"] else 0.0 for s in answerable]
    out["mrr"] = _rate(reciprocal)
    out["mrr_ci95"] = _interval(reciprocal)
    out["abstention_rate"] = _rate([1.0 if s["not_sure"] else 0.0 for s in unanswerable])
    out["over_abstention_rate"] = _rate([1.0 if s["not_sure"] else 0.0 for s in answerable])
    out["false_confident_rate"] = _rate([
        0.0 if s["answerable"] and s["gold_rank"] and s["gold_rank"] <= 3 else 1.0 for s in answered])
    out["recall@3_when_answered"] = _rate([
        1.0 if s["gold_rank"] and s["gold_rank"] <= 3 else 0.0 for s in answered if s["answerable"]])
    return out


def summarise_groups(scored: list[dict]) -> dict:
    return {g: summarise([s for s in scored if g == "all" or s["language"] == g]) for g in GROUPS}


def run_questions(questions: list[dict], search, chunks: dict[str, dict]) -> list[dict]:
    return [score_question(q, resolve_gold_ids(q, chunks), search(q["question"])) for q in questions]


def sweep(scored: list[dict], thresholds: list[float] | None = None) -> dict:
    """What each possible threshold would do, per language. Reports only: it sets nothing."""
    thresholds = thresholds or SWEEP_THRESHOLDS
    out: dict = {}
    for group in GROUPS:
        members = [s for s in scored if group == "all" or s["language"] == group]
        rows = []
        for t in thresholds:
            applied = [{**s, "not_sure": s["confidence"] < t} for s in members]
            m = summarise(applied)
            rows.append({"threshold": t, "shown_share": round(m["n_answered"] / m["n"], 4) if m["n"] else None,
                         "abstention_rate": m["abstention_rate"], "over_abstention_rate": m["over_abstention_rate"],
                         "false_confident_rate": m["false_confident_rate"], "recall@3_when_answered": m["recall@3_when_answered"]})
        out[group] = rows
    return out


def feature_means(scored: list[dict]) -> dict:
    """Mean of each feature where the tool was right, and where it was not, per language."""
    out: dict = {}
    for group in GROUPS:
        members = [s for s in scored if group == "all" or s["language"] == group]
        right = [s for s in members if s["answerable"] and s["gold_rank"] and s["gold_rank"] <= 3]
        wrong = [s for s in members if not (s["answerable"] and s["gold_rank"] and s["gold_rank"] <= 3)]
        names = list(config.CONFIDENCE_WEIGHTS)
        out[group] = {"n_right": len(right), "n_wrong": len(wrong)}
        for name, values in (("right", right), ("wrong", wrong)):
            out[group][name] = {k: _rate([v["features"][k] for v in values]) for k in names}
            out[group][name]["confidence"] = _rate([v["confidence"] for v in values])
    return out


def settings() -> dict:
    return {"rrf_k": config.RRF_K, "rrf_weight_bm25": config.RRF_WEIGHT_BM25,
            "rrf_weight_embedding": config.RRF_WEIGHT_EMBEDDING,
            "confidence_weights": config.CONFIDENCE_WEIGHTS,
            "not_sure_confidence_threshold": config.NOT_SURE_CONFIDENCE_THRESHOLD,
            "main_results": config.MAIN_RESULTS, "side_block_max": config.SIDE_BLOCK_MAX,
            "embedding_model": config.EMBEDDING_MODEL_NAME, "embedding_revision": config.EMBEDDING_MODEL_REVISION}


def _git(args: list[str], root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _commit(root: Path) -> str:
    return _git(["rev-parse", "--short", "HEAD"], root).stdout.strip() or "nogit"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _table(groups: dict) -> str:
    rows = [("n", "n"), ("answerable", "n_answerable"), ("unanswerable", "n_unanswerable"), ("recall@1", "recall@1"),
            ("recall@3", "recall@3"), ("recall@5", "recall@5"), ("MRR", "mrr"), ("abstention rate", "abstention_rate"),
            ("over-abstention rate", "over_abstention_rate"), ("false-confident rate", "false_confident_rate"),
            ("recall@3 when answered", "recall@3_when_answered")]
    lines = [f"{'metric':<24}" + "".join(f"{g:>10}" for g in GROUPS)]
    for label, key in rows:
        cells = "".join(f"{'—' if groups[g][key] is None else groups[g][key]:>10}" for g in GROUPS)
        lines.append(f"{label:<24}{cells}")
    return "\n".join(lines)


def _write(name: str, payload: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def run_dev(search=None, directory: Path = QUESTIONS_DIR) -> int:
    """Run the dev split. There is deliberately no way to pass another file."""
    path = directory / "dev.jsonl"
    rows = load_split("dev", directory)
    if not rows:
        print("No dev questions yet: eval/questions/dev.jsonl is missing or empty. Nothing was run.")
        return 1
    chunks = load_chunks()
    errs = validate_set(rows, chunks)
    errs += [f"{r['id']}: not a dev row" for r in rows if r["split"] != "dev"]
    if errs:
        print("Dev questions are invalid:\n" + "\n".join(errs))
        return 1
    if search is None:
        search = _default_search()
    scored = run_questions(rows, search, chunks)
    groups = summarise_groups(scored)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = _write(f"{stamp}_{_commit(config.ROOT)}_dev.json",
                 {"split": "dev", "questions_sha256": file_sha256(path), "settings": settings(),
                  "summary": groups, "questions": scored})
    print(_table(groups))
    if config.NOT_SURE_CONFIDENCE_THRESHOLD is None:
        print("\nNo threshold is set, so nothing was withheld: abstention rates are 0 by construction.")
    print(f"\nSaved {out.relative_to(config.ROOT)}")
    return 0


def confidence_report(search=None, directory: Path = QUESTIONS_DIR) -> int:
    """Dev only. Shows what thresholds would do, per language. Never changes config."""
    rows = load_split("dev", directory)
    if not rows:
        print("No dev questions yet: eval/questions/dev.jsonl is missing or empty. Nothing was run.")
        return 1
    chunks = load_chunks()
    errs = validate_set(rows, chunks) + [f"{r['id']}: not a dev row" for r in rows if r["split"] != "dev"]
    if errs:
        print("Dev questions are invalid:\n" + "\n".join(errs))
        return 1
    if search is None:
        search = _default_search()
    scored = run_questions(rows, search, chunks)
    table = sweep(scored)
    means = feature_means(scored)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = _write(f"{stamp}_{_commit(config.ROOT)}_dev_confidence.json",
                 {"split": "dev", "questions_sha256": file_sha256(directory / "dev.jsonl"), "settings": settings(),
                  "feature_means": means, "sweep": table})
    for group in GROUPS:
        print(f"\n{group}: {means[group]['n_right']} right, {means[group]['n_wrong']} not right (top 3)")
        print(f"  {'threshold':>9} {'shown':>7} {'abstain':>8} {'over-abstain':>13} {'false-conf':>11} {'recall@3 shown':>15}")
        for r in table[group]:
            cells = [r["shown_share"], r["abstention_rate"], r["over_abstention_rate"], r["false_confident_rate"], r["recall@3_when_answered"]]
            shown = ["—" if c is None else c for c in cells]
            print(f"  {r['threshold']:>9} {shown[0]:>7} {shown[1]:>8} {shown[2]:>13} {shown[3]:>11} {shown[4]:>15}")
    print(f"\nSaved {out.relative_to(config.ROOT)}. This report sets nothing: choose the threshold from it and set it in config.py.")
    return 0


def final_preconditions(root: Path, directory: Path, results_dir: Path = RESULTS_DIR) -> tuple[str | None, list[str]]:
    """Return (hash, problems). The frozen file and its hash must be committed and unchanged."""
    data, stamp = directory / "test.jsonl", directory / "test.sha256"
    problems: list[str] = []
    if not data.exists():
        problems.append(f"{data.name} does not exist")
    if not stamp.exists():
        problems.append(f"{stamp.name} does not exist; run scripts/freeze_test.py and commit both files")
    if problems:
        return None, problems
    for path in (data, stamp):
        rel = str(path.relative_to(root))
        if _git(["ls-files", "--error-unmatch", rel], root).returncode != 0:
            problems.append(f"{rel} is not committed")
        elif _git(["diff", "--quiet", "HEAD", "--", rel], root).returncode != 0:
            problems.append(f"{rel} differs from the committed version")
    committed = stamp.read_text().strip()
    actual = file_sha256(data)
    if committed != actual:
        problems.append(f"hash mismatch: committed {committed[:12]}, file is {actual[:12]}")
    if results_dir.exists() and list(results_dir.glob(f"final_{actual[:12]}_*.json")):
        problems.append("a final run for this frozen file already exists; it runs once")
    return actual, problems


def run_final(flag: bool, search=None, root: Path = config.ROOT, directory: Path = QUESTIONS_DIR,
              results_dir: Path = RESULTS_DIR) -> int:
    if not flag:
        print("The test split runs only with --final. Nothing was run.")
        return 2
    digest, problems = final_preconditions(root, directory, results_dir)
    if config.NOT_SURE_CONFIDENCE_THRESHOLD is None:
        problems.append("NOT_SURE_CONFIDENCE_THRESHOLD is not set; set it from the dev set first")
    if problems:
        print("Refusing the final run:\n" + "\n".join(f"- {p}" for p in problems))
        return 2
    rows = load_split("test", directory)
    chunks = load_chunks()
    errs = validate_set(rows, chunks)
    if errs:
        print("Test questions are invalid:\n" + "\n".join(errs))
        return 2
    if search is None:
        search = _default_search()
    scored = run_questions(rows, search, chunks)
    groups = summarise_groups(scored)
    results_dir.mkdir(parents=True, exist_ok=True)
    out = results_dir / f"final_{digest[:12]}_{_commit(root)}.json"
    out.write_text(json.dumps({"split": "test", "questions_sha256": digest, "settings": settings(), "summary": groups,
                               "questions": scored}, indent=2, ensure_ascii=False))
    print(_table(groups))
    print(f"\nSaved {out}")
    return 0


def _default_search():
    from ph_privacy_guide.offline import enforce_offline

    enforce_offline()
    from ph_privacy_guide.retrieve.search import Searcher

    searcher = Searcher()
    return lambda text: searcher.search(text, k=TOP_K)
