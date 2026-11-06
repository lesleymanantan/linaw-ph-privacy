# ph-privacy-guide

A local, offline tool that finds the passages of Philippine data privacy law and National Privacy
Commission (NPC) issuances that relate to a plain-language question in English or Filipino. It
shows the exact text with its source, its type (Law, Binding rule, NPC guidance, NPC summary, Draft, not
law, or "Rule (marked superseded, see warning)" where an NPC annotation says so) and its status, and says **"Not sure"** when confidence is low.

Status labels mean what they say and no more. "NPC lists this document and notes no repeal. We have not
checked it ourselves." (recorded in the catalogue as "Listed by NPC, no repeal noted; not independently
verified") means the document is on the NPC advisories and circulars page with no repeal marked, and no
repeal of it was found in this corpus. It does not prove the document is current: that page also lists
repealed circulars with no repeal note. "Not verified" means no status has been established. "Amended by
NPC Circular 2020-03 (per NPC annotations in the text)" rests on annotations printed in the later annotated
copy of the IRR used here; the rest of that text is not independently verified. No label says a document is
in force, except the draft's "draft, not in force".

> **Status: early development.** Hybrid search and a local page work, but search quality has not been
> measured yet. **"Not sure" is not active:** its threshold will be set on the human-written dev questions,
> and until then the tool always shows passages and says that they may not answer the question.

## ⚠ Not legal advice

This tool helps you locate and read source texts. **It is not legal advice** and does not create a
lawyer–client relationship. Retrieval can miss relevant provisions or return irrelevant ones, and
statuses are only as current as the catalogue date. Always read the full instrument and check the
NPC website (privacy.gov.ph) for current versions. For decisions about your situation, consult a
qualified lawyer or your Data Protection Officer.

## How it works

- **No LLM is used inside the tool.** It does not generate, summarise or interpret text. It ranks
  existing passages using keyword search (BM25) and a small multilingual embedding model, and shows
  them verbatim.
- **Runs fully offline** on a laptop CPU. No telemetry, no network calls at runtime. Your questions
  never leave your machine.
- Draft instruments are always labelled **"draft, not in force"**. Passages from repealed texts are
  flagged with the name of the replacing instrument.
- **Fixed layout.** Passages are chosen by relevance (BM25 and embeddings, combined by reciprocal rank
  fusion with k=60 and equal weights). The main block shows the top 3 statutes, rules and guidance that
  are not repealed or draft, each with its status label. Below it, two labelled blocks may appear:
  "Pending change: draft, not law" and "NPC summary, not the rule text", at most one passage each, and only
  if the passage scores at least as high as the last one in the main block. This layout is set in
  `config.py` and is not tuned on any questions.

## Scope

Collection `privacy-law` (on by default):

- Republic Act No. 10173 (Data Privacy Act of 2012) and its Implementing Rules and Regulations
- Selected NPC circulars (rules) and advisories (guidance)
- One NPC Privacy Toolkit chapter (educational guidance; may predate later advisories)
- One draft circular (not law)

Out of scope: court decisions, NPC decisions and resolutions, sector-specific laws, and any
issuance not listed in `catalogue/catalogue.csv`. A `national-ai-policy` collection may be added
later.

## Repository layout

```
catalogue/catalogue.csv     one row per document (status, authority, sha256, source)
src/ph_privacy_guide/       ingest/ index/ retrieve/ answer/ app/
reports/                    extraction report (section validation: data/processed/)
eval/                       question schema, guidelines, template; human-written questions
data/glossary/              English defined terms; Filipino values come only from people, via scripts/import_glossary.py
results/                    evaluation and benchmark runs
scripts/                    dev-only tools: model download, question import, metrics, benchmark
SOURCES.md  MODELS.md       provenance of legal texts and downloaded models
```

The source PDFs (`data/raw/`) are not redistributed in this repository.

## How to run

Everything runs on your computer, with no network. These commands need the setup below to have been done
once.

Start the local page, then open http://127.0.0.1:8765/ in your browser. Press Ctrl-C to stop it.

```sh
cd ph-privacy-guide
.venv/bin/python -m ph_privacy_guide.app.web
```

Add `--port 9000` if that port is in use. Or search from the command line:

```sh
.venv/bin/python -m ph_privacy_guide.app.cli "your question"
```

Both show each passage's exact text with its type, status, source and any warnings. The page binds to
127.0.0.1 only, loads nothing from elsewhere and does not log searches. When "Not sure" is active it shows a
plain link to the National Privacy Commission's contact page, which opens only if you follow it.

The page also has:

- **Official document links.** "Open the official document" opens the address in `catalogue/catalogue.csv` in
  a new tab, at the right page for a PDF. The tool never fetches it. A link appears only for an https address
  on privacy.gov.ph; addresses are never guessed. They come from `data/reference/npc_page_links_5Nov.csv`.
  RA 10173, the IRR, the draft circular and the Toolkit are not in that list, so they show no link.
- **Abbreviation hints.** Abbreviations the documents define, such as DPO, PIC and DPA, show their full names
  when you hover over them in passages, annotations, warnings and notes. This changes the display only, not
  the stored text. `reports/abbreviation_sources.csv` gives the passage behind each one.
- **An EN/FIL switch for interface labels.** Labels are in `data/i18n/labels.csv`. An empty `fil` cell falls
  back to English, and the column is empty for now, so both settings look the same until people fill it in.
  Passages, warnings and notes stay in their original English and are never translated.

## Setup (development)

uv is a development prerequisite, and it is installed inside this folder. `scripts/uv` keeps uv's
cache, its Python and any home-directory writes under `.tools/` (gitignored), so nothing is written
outside the project. The source PDFs go in `data/raw/` and are not part of this repository.

```sh
python3 -m venv .tools && .tools/bin/pip install --no-cache-dir uv==0.9.5
scripts/uv sync
.venv/bin/python scripts/download_model.py             # once, needs network; see MODELS.md
.venv/bin/python -m ph_privacy_guide.ingest.extract    # per-page text, extraction report
.venv/bin/python -m ph_privacy_guide.ingest.sectioner  # sections, footnotes, validation report
.venv/bin/python -m ph_privacy_guide.ingest.chunker    # chunks.jsonl, gold labels, validation report
.venv/bin/python -m ph_privacy_guide.index.bm25        # keyword index
.venv/bin/python -m ph_privacy_guide.index.embed       # embedding index
.venv/bin/python scripts/scan_status_language.py       # repeal and amendment language, for status review
.venv/bin/pytest
```

## Evaluation

See `eval/GUIDELINES.md`. The repository has no evaluation questions yet: people write them.

## AI in this tool

No AI model is used by the tool itself at runtime other than the local
embedding model listed in `MODELS.md`.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
