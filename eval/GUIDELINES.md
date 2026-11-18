# Evaluation guidelines

How to write, label and run evaluation questions. This file contains no example questions on
purpose. Examples steer how people write.

## Who writes what

| Split | Written by | Used for | Rules |
|---|---|---|---|
| `train` | Code from headings and definitions (`source=rule`), or people | Checks during development | Rule rows only appear here |
| `dev` | People | Setting the "not sure" threshold, comparing changes | `origin` human or `ai_draft_edited`; `reviewer` required |
| `test` | People | One final run | `origin=human` only; `reviewer` required; frozen before it is run |

AI tools must not write, draft or suggest questions. An `ai_draft_edited` row is allowed in `dev`
only if a person edited and reviewed it, and it must be marked as such.

## Writing questions

1. Write the question before searching for the answer, and without seeing the tool's results.
2. Use the words a person outside the legal field would use. Do not copy wording from the documents.
3. Filipino and Taglish questions must be written by native speakers, not machine-translated.
4. Cover all three languages. To compare languages directly, write the same question in each and
   give the rows the same `pair_id`. A `pair_id` may not cross splits.
5. About one in five questions should be unanswerable (`answerable` = `no`). These measure "not sure".
   A question that is not about data privacy has `type` = `out_of_scope`. A data privacy question this
   corpus does not answer keeps `type` = `lookup` or `scenario`, or may be marked `out_of_scope`.
6. Spread questions across the instruments and topics. Do not cluster on one document.

## Labelling gold passages

1. Search the documents themselves, not only this tool, to find the passage that answers the question.
2. Put it in the `gold` column as a label from `eval/gold_labels.csv`: the instrument key and section
   path, such as `NPC_Circular_2022-04 s.7`. Separate several with `;`. Any one counts as a hit.
   A label for a section counts a hit on any chunk of that section; a label for a subsection, such as
   `RA10173 s.3(l)`, only on that subsection.
3. List every passage that fully answers the question, including one in a different instrument.
4. Prefer the operative provision. Label a draft passage or the 16-03 Summary as gold only if it is
   truly the only answer. A passage from a draft is not law.
5. Unanswerable questions have an empty `gold` and `answerable` set to `no`.
6. A second person checks each row and is named in `reviewer`.

Labels come from the documents, so they survive re-chunking. The import fails as a whole if any label
does not resolve, and the metrics commands check them again.

## Columns

Start from `eval/questions_template.csv`. Full definitions are in `eval/question_schema.json`. All 12
columns must be present, and no others. A row with an empty `question` is skipped, however much else is
filled in, so unfinished rows can stay in the file. The import lists any it skipped, apart from fully blank ones.

| Column | Values | Stored as |
|---|---|---|
| `id` | Unique across all splits | `id` |
| `question` | The question | `question` |
| `language` | `en`, `fil`, `taglish` | `language` |
| `pair_id` | Optional | `pair_id` |
| `type` | `lookup`, `scenario`, `out_of_scope` | `type` |
| `answerable` | `yes` or `no`; `no` for every `out_of_scope` row | `answerable`, true or false |
| `gold` | Labels from `eval/gold_labels.csv`, separated by `;` | `gold` |
| `origin` | `human`, `ai_draft_edited` | `origin` |
| `writer` | Name or initials | `author` |
| `reviewer` | Name or initials; required for `dev` and `test` | `reviewer` |
| `date` | Free text | `date` |
| `notes` | Anything; for people only | Not read |

Imported rows are stored with `source=human`. Rows with `source=rule` come from code, not from this CSV,
and stay in `train`.

## Commands

```sh
.venv/bin/python scripts/import_questions.py my_questions.csv --split dev   # all rows valid, or nothing written
.venv/bin/python scripts/evaluate.py                                        # dev only; takes no file argument
.venv/bin/python scripts/confidence_report.py                               # dev only; what thresholds would do
.venv/bin/python scripts/freeze_test.py                                     # writes eval/questions/test.sha256
.venv/bin/python scripts/evaluate_final.py --final                          # test, once
.venv/bin/python scripts/evaluate_final.py --final --allow-no-threshold     # test, once, with no threshold set
```

## The test split

1. Finish all tuning on `dev` first. Nothing is ever tuned on `test`, and neither are the sample searches.
2. Import `test.csv`, run `freeze_test.py`, and commit `test.jsonl` and `test.sha256` together.
3. `evaluate_final.py` runs only with `--final`, only if both files are committed and unchanged and the
   hash matches, and only once per frozen file. It also needs a "not sure" threshold, unless you pass
   `--allow-no-threshold`. With that option the run goes ahead without a threshold, every question gets
   results, and the result file records that no threshold was set and that abstention is 0 by construction.
4. Report the result as it is, whatever it is. If the test questions change, say so in the report.

## Metrics

Each is reported overall and for `en`, `fil` and `taglish`, with the number of questions. Small groups
give wide ranges, so 95% bootstrap intervals are shown for recall and MRR.

| Metric | Meaning | Over |
|---|---|---|
| Recall@1, 3, 5 | A gold passage is in the top 1, 3 or 5 of the main block's ranking. The reader sees the top 3 | Answerable |
| MRR | Average of 1 / rank of the first gold passage in the top 5; 0 if none | Answerable |
| Abstention rate | The tool said "not sure" | Unanswerable |
| Over-abstention rate | The tool said "not sure" when an answer exists | Answerable |
| False-confident rate | The tool showed passages, but the question was unanswerable or no gold passage was in the top 3 | All questions where passages were shown |
| Recall@3 when answered | Recall@3, counting only questions where passages were shown | Answerable and answered |

Recall measures the ranking even when "not sure" hides it from the reader. The abstention and
false-confident rates measure what the reader actually sees. A gold passage shown only in a side block
(draft or Summary) does not count towards recall; each result records it as `gold_in_side_block`.

## Setting the "not sure" threshold

Confidence combines five features: the top fused score, the margin to the second result, BM25 and
embedding agreement, the top embedding cosine, and term overlap. Term overlap is one feature, never a gate.
`scripts/confidence_report.py` shows what each threshold would do for `en`, `fil` and `taglish`, and how each
feature differs between right and wrong results. It sets nothing. Choose the threshold from `dev` only and set
`NOT_SURE_CONFIDENCE_THRESHOLD` in `config.py`. Until then nothing is withheld, and the tool says so.
