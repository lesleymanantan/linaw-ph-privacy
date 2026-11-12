# Changelog

## 2026-11-12

- **Renamed to Linaw.** The project is now called Linaw, and the repository and package name is
  `linaw-ph-privacy` (was `ph-privacy-guide`). Changed: README title and setup line, NOTICE, the page title in
  `data/i18n/labels.csv`, `pyproject.toml`, `uv.lock`, the package docstring and the offline error message.
  The README now says "Linaw is Filipino for 'clarity'." The Python module stays `ph_privacy_guide`, so all
  commands are unchanged. Legal document names, citations and source URLs are unchanged.
- **Backup.** Branch `backup-nov12-pre-rename` (`c17c2d4`) pushed to origin before the rename.
- **Glossary freeze.** `data/glossary/GLOSSARY_FREEZE.md` records the sha256 of `en_fil_terms.csv` and its 8
  filled rows as of 2026-11-11.

## 2026-11-09

- **Dev set.** 49 human-written dev questions imported locally into `eval/questions/dev.jsonl`
  (22 English, 7 Filipino, 20 Taglish; 39 with gold, 10 without). The file is not committed.
  Baseline with the glossary off: recall@3 0.28 overall (English 0.50, Taglish 0.13, Filipino 0).
  No "not sure" threshold is set, so abstention is 0 by construction.
- **Glossary.** First 8 reviewed Filipino rows added to `data/glossary/en_fil_terms.csv` through
  `scripts/import_glossary.py` (44 phrases). `USE_GLOSSARY` stays `False`. With it on, the same dev set gave
  recall@3 0.36 overall (Taglish 0.20, Filipino 0.33, English unchanged at 0.50).
- **Tests.** Evaluation tests no longer depend on local dev questions: the "no questions committed" check
  uses `git ls-files eval/questions`, and the script checks run against an empty temporary folder, so they
  never read `dev.jsonl` or write into `results/eval/`. Dev evaluation outputs in `results/eval/` are now
  gitignored; `final_*.json` stays committable.
- **Source addresses.** RA 10173, the IRR, the draft circular and the Toolkit now have official addresses,
  supplied by the project owner and checked against the saved copies (same sha256), with `retrieved_on`
  2026-11-09. All 32 catalogue rows now have an address.
- **History rewritten.** The commit history was rewritten on 9 Nov 2026. Every commit hash changed, and
  hashes quoted from before then (including the one in `results/bench/2026-11-05_6516403.json`) no longer exist.
- **Remote.** Pushed `master` and `backup-nov09-after-rewrite` to a private GitHub repository.
