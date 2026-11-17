# Pending

Open items as of 2026-11-17.

## Done since 2026-11-09
- The GitHub repository is renamed to `linaw-ph-privacy`, and the local remote points at
  `https://github.com/lesleymanantan/linaw-ph-privacy.git`. Push and pull work. It stays private for now.
- The glossary freeze is recorded in `data/glossary/GLOSSARY_FREEZE.md` (sha256 of `en_fil_terms.csv` and its
  8 filled rows, 2026-11-11).
- The test guard is changed: `test_repository_holds_no_questions` allows exactly `eval/questions/test.jsonl` and
  `eval/questions/test.sha256`, and nothing else under `eval/questions/`.
- `USE_GLOSSARY` is decided: `True`, with all 8 reviewed rows kept (see CHANGELOG, 2026-11-17).

## Known limits for the final run
- `NOT_SURE_CONFIDENCE_THRESHOLD` stays `None` for the final run. "Not sure" is not active, so every search
  shows results, and abstention is 0 by construction.

## Rename leftovers
- The local folder is still named `ph-privacy-guide`.
- After the final test run: change the title in `eval/question_schema.json` from "ph-privacy-guide evaluation
  question" to the new name. `eval/` stays untouched until then.

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
