# Pending

Open items as of 2026-11-18.

## Done since 2026-11-09
- The GitHub repository is renamed to `linaw-ph-privacy`, and the local remote points at
  `https://github.com/lesleymanantan/linaw-ph-privacy.git`. Push and pull work. It stays private for now.
- The glossary freeze is recorded in `data/glossary/GLOSSARY_FREEZE.md` (sha256 of `en_fil_terms.csv` and its
  8 filled rows, 2026-11-11).
- The test guard is changed: `test_repository_holds_no_questions` allows exactly `eval/questions/test.jsonl` and
  `eval/questions/test.sha256`, and nothing else under `eval/questions/`.
- `USE_GLOSSARY` is decided: `True`, with all 8 reviewed rows kept (see CHANGELOG, 2026-11-17).
- The test split is frozen (`8c78b43`), and the final run is done once, with `--allow-no-threshold`:
  `results/eval/final_8937357c5b76_8c78b43.json`. Recall@3 is 0.41 overall (CHANGELOG, 2026-11-17). It must not be
  run again on this frozen file.
- The title in `eval/question_schema.json` is now "Linaw evaluation question" (`46052ab`).
- `eval/GUIDELINES.md` now describes `--allow-no-threshold` for the final run (`f9bd5dc`).
- The freeze, the final result and the notes are pushed to `origin/master` (up to `f9bd5dc`).

## Known limits of the final result
- No "not sure" threshold was set. Every question got results, so abstention is 0 by construction, and the
  false-confident rate is 0.63 overall.
- The test set is small (30 questions, 27 answerable, 7 to 10 per language), so the 95% intervals are wide.
- Filipino is the weakest group (recall@3 0.29, 7 answerable questions).
- The glossary, RRF settings and result layout were fixed before the test split was imported. Nothing was tuned
  on it.

## Rename leftovers
- The local folder is still named `ph-privacy-guide`.

## Evaluation and tuning (dev set only)
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
