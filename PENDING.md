# Pending

Open items as of 2026-11-09.

## Before freezing the test split
- `tests/test_evaluate.py::test_repository_holds_no_questions` fails if any file under `eval/questions/` is
  committed. `eval/GUIDELINES.md` says to commit `test.jsonl` and `test.sha256` when freezing, so the test must
  first be changed to allow exactly those two files.

## Evaluation and tuning (dev set only)
- Set `NOT_SURE_CONFIDENCE_THRESHOLD` from the dev set. It is still `None`.
- Decide on `USE_GLOSSARY` from the dev results. The `DPO` entry improved two DPO questions (DEV-016, DEV-036)
  but pushed three registration questions down (DEV-003, DEV-014, DEV-034). `privacy notice` fired five times
  and changed nothing.
- Revisit whether the superseded IRR s.20 should still rank first.

## Catalogue and sources
- `retrieved_on` is `TBS` on the 28 rows filled from the NPC links list.
- NPC Advisory 2022-01 (requests for personal data of public officers) is on the NPC page but not in the
  catalogue or corpus.
- The NPC page note naming Circular 2024-02 as repealing Advisory 2020-04 is recorded; the basis is unchanged.

## Housekeeping
- `results/bench/2026-11-05_6516403.json` is named after a commit hash that no longer exists after the history
  rewrite. The benchmark has not been re-run since one chunk's text changed.
- `.tools/tmp/old-dot-git-9Nov` (the pre-rewrite history) and `.tools/tmp/public-clone` are kept as fallbacks.
  They are gitignored; delete them when no longer needed.
