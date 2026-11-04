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
5. About one in five questions should be unanswerable: `out_of_scope` (not data privacy) or
   `not_covered` (data privacy, but not in this corpus). These measure "not sure".
6. Spread questions across the instruments and topics. Do not cluster on one document.

## Labelling gold passages

1. Search the documents themselves, not only this tool, to find the passage that answers the question.
2. Put it in the `gold` column as the citation exactly as the tool prints it, or as the `chunk_id`
   from `data/processed/chunks.jsonl`. Separate several with `;`. Any one counts as a hit.
3. List every passage that fully answers the question, including one in a different instrument.
4. Prefer the operative provision. Label a draft passage or the 16-03 Summary as gold only if it is
   truly the only answer. A passage from a draft is not law.
5. Unanswerable questions have an empty `gold` and `answerable` set to `false`.
6. A second person checks each row and is named in `reviewer`.

If the documents are re-chunked, chunk ids can change. The import and metrics commands reject gold
ids that no longer exist, and those rows must be re-labelled.

## Columns

Start from `eval/questions_template.csv`. Full definitions are in `eval/question_schema.json`.

| Column | Values |
|---|---|
| `id` | Unique across all splits |
| `question` | The question |
| `language` | `en`, `fil`, `taglish` |
| `type` | `definition`, `obligation`, `right`, `procedure`, `penalty`, `scenario`, `status`, `out_of_scope`, `not_covered` |
| `answerable` | `true` or `false`; `false` only for `out_of_scope` and `not_covered` |
| `gold` | Citations or chunk ids, separated by `;` |
| `source` | `human`, or `rule` for code-generated rows (`train` only) |
| `origin` | `human`, `ai_draft_edited`; empty only for `source=rule` |
| `author`, `reviewer` | Names or initials |
| `pair_id`, `topic`, `notes` | Optional |

## Commands

```sh
.venv/bin/python scripts/import_questions.py my_questions.csv --split dev   # all rows valid, or nothing written
.venv/bin/python scripts/evaluate.py                                        # dev only; takes no file argument
.venv/bin/python scripts/freeze_test.py                                     # writes eval/questions/test.sha256
.venv/bin/python scripts/evaluate_final.py --final                          # test, once
```

## The test split

1. Finish all tuning on `dev` first. Nothing is ever tuned on `test`, and neither are the sample searches.
2. Import `test.csv`, run `freeze_test.py`, and commit `test.jsonl` and `test.sha256` together.
3. `evaluate_final.py` runs only with `--final`, only if both files are committed and unchanged and the
   hash matches, and only once per frozen file. It refuses a second run.
4. Report the result as it is, whatever it is. If the test questions change, say so in the report.

## Metrics

Each is reported overall and for `en`, `fil` and `taglish`, with the number of questions. Small groups
give wide ranges, so 95% bootstrap intervals are shown for recall and MRR.

| Metric | Meaning | Over |
|---|---|---|
| Recall@1, 3, 5 | A gold passage is in the top 1, 3 or 5, in the order shown to the reader | Answerable |
| MRR | Average of 1 / rank of the first gold passage in the top 5; 0 if none | Answerable |
| Abstention rate | The tool said "not sure" | Unanswerable |
| Over-abstention rate | The tool said "not sure" when an answer exists | Answerable |
| False-confident rate | The tool showed passages, but the question was unanswerable or no gold passage was in the top 3 | All questions where passages were shown |
| Recall@3 when answered | Recall@3, counting only questions where passages were shown | Answerable and answered |

Recall measures the ranking even when "not sure" hides it from the reader. The abstention and
false-confident rates measure what the reader actually sees.
