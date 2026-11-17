# Changelog

## 2026-11-17

- **Test split frozen.** 30 human-written test questions (10 English, 9 Filipino, 11 Taglish; 27 answerable,
  3 not; all `origin=human`) imported to `eval/questions/test.jsonl`, with `test.sha256`
  (`8937357c5b76…`), committed together in `8c78b43`.
- **Final run.** `scripts/evaluate_final.py --final --allow-no-threshold`, run once at `8c78b43`. Result:
  `results/eval/final_8937357c5b76_8c78b43.json`. Settings: glossary on, RRF k=60 with equal weights, no "not
  sure" threshold. Figures over answerable questions, with 95% bootstrap intervals:

  | | All (27) | English (10) | Filipino (7) | Taglish (10) |
  |---|---|---|---|---|
  | Recall@1 | 0.33 [0.15, 0.52] | 0.40 [0.10, 0.70] | 0.14 [0.00, 0.43] | 0.40 [0.10, 0.70] |
  | Recall@3 | 0.41 [0.22, 0.59] | 0.40 [0.10, 0.70] | 0.29 [0.00, 0.57] | 0.50 [0.20, 0.80] |
  | Recall@5 | 0.48 [0.30, 0.67] | 0.60 [0.30, 0.90] | 0.29 [0.00, 0.57] | 0.50 [0.20, 0.80] |
  | MRR | 0.39 [0.21, 0.56] | 0.45 [0.15, 0.72] | 0.21 [0.00, 0.50] | 0.45 [0.20, 0.75] |

  Abstention is 0 by construction, because no threshold is set. The false-confident rate is 0.63 overall.
- **`--allow-no-threshold`.** The final run can now go ahead without a "not sure" threshold, but only with this
  option. The result file records that no threshold was set and that abstention is 0 by construction, and the
  run stops without saving if any result says "not sure" anyway.
- **Glossary expansion on.** `USE_GLOSSARY` is now `True`, a decision by the project owner. All 8 reviewed rows
  (44 phrases) are kept. Untuned dev figures, same 49-question dev set (39 with gold), glossary off then on:

  | Recall@3 | Off | On |
  |---|---|---|
  | All (39) | 0.28 | 0.36 |
  | English (18) | 0.50 | 0.50 |
  | Taglish (15) | 0.13 | 0.20 |
  | Filipino (6) | 0 | 0.33 |

  Eight dev questions changed rank (rank of the first gold passage in the full list, off then on):

  | Question | Language | Phrase | Rank |
  |---|---|---|---|
  | DEV-016 | Filipino | DPO | 6 to 1 |
  | DEV-018 | Taglish | magparegister | 10 to 1 |
  | DEV-036 | Filipino | DPO | 7 to 3 |
  | DEV-012 | English | hacked | 82 to 26 |
  | DEV-013 | Taglish | security breach | 75 to 71 |
  | DEV-014 | English | DPO | 2 to 3 (worse) |
  | DEV-003 | English | DPO | 15 to 18 (worse) |
  | DEV-034 | Taglish | DPO | 10 to 13 (worse) |

  `privacy notice` matched five questions and changed nothing. The glossary tests now pass the switch
  explicitly where they compare on and off.
- **Test guard.** `test_repository_holds_no_questions` now allows exactly `eval/questions/test.jsonl` and
  `eval/questions/test.sha256` to be committed, and nothing else under `eval/questions/`.
- **ROADMAP.md added**, listing known gaps and open questions.
- Local `dost_questions.txt` and `dost_results.txt` are gitignored.

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
