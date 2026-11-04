# MODELS.md

Every downloaded model is logged here at download time. Only models approved by the project owner are
downloaded, by the dev-only `scripts/download_model.py`. The tool loads them from local files and makes
no network calls at runtime. Licence is as stated on the model card.

| Model | Revision | Size on disk | Licence (model card) | Source URL | Downloaded | model.onnx sha256 | Purpose |
|---|---|---|---|---|---|---|---|
| intfloat/multilingual-e5-small | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | 487.8 MB (5 files; model.onnx 470.3 MB) | mit | https://huggingface.co/intfloat/multilingual-e5-small | 2026-11-05 | `ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665` | Passage and query embeddings for hybrid retrieval |
