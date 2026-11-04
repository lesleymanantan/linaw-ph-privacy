# ph-privacy-guide

A local, offline tool that finds the passages of Philippine data privacy law and National Privacy
Commission (NPC) issuances that relate to a plain-language question in English or Filipino. It
shows the exact text with its citation, authority tag (statute, rule, guidance, policy, draft) and
status (in force, repealed, amended, draft, unverified), and says **"Not sure"** when confidence is
low.

> **Status: early development.** Ingestion and cataloguing only; retrieval is not built yet.

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
eval/questions/             human-written dev/test questions
SOURCES.md  MODELS.md       provenance of legal texts and downloaded models
```

The source PDFs (`data/raw/`) are not redistributed in this repository.

## Setup (development)

```sh
scripts/uv sync          # project-local uv: cache and Python stay inside this folder
.venv/bin/python -m ph_privacy_guide.ingest.extract   # extraction report
.venv/bin/python -m ph_privacy_guide.ingest.sectioner # section validation report
.venv/bin/pytest
```

## AI assistance

No AI model is used by the tool itself at runtime other than the local
embedding model listed in `MODELS.md`.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
