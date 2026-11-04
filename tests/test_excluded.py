"""data/raw/excluded/ must never appear in any derived artefact.

Checks file paths and doc_ids in: the catalogue, data/processed/ (pages, sections, chunks)
and indexes/. Scans only those artefacts; never lists data/raw/excluded/ itself.
"""
import json

from ph_privacy_guide import catalogue
from ph_privacy_guide.config import ALLOWED_COLLECTIONS, EXCLUDED_DIRNAME, PROCESSED, ROOT, allowed_pdfs

MARKER = f"raw/{EXCLUDED_DIRNAME}/"


def _allowed_doc_ids():
    return {p.stem for p in allowed_pdfs()}


def test_allowlist_has_no_excluded():
    assert EXCLUDED_DIRNAME not in ALLOWED_COLLECTIONS
    for p in allowed_pdfs():
        assert p.relative_to(ROOT / "data" / "raw").parts[0] in ALLOWED_COLLECTIONS


def test_catalogue_has_no_excluded_paths():
    for r in catalogue.load():
        assert MARKER not in r["file_path"]
        assert EXCLUDED_DIRNAME not in r["file_path"].split("/")


def test_processed_and_indexes_have_no_excluded():
    allowed = _allowed_doc_ids()
    for base in (PROCESSED, ROOT / "indexes"):
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix == ".jsonl":
                assert f.stem in allowed | {"chunks"}, f"unexpected document file {f}"
                for line in f.open():
                    rec = json.loads(line)
                    assert rec.get("doc_id") in allowed, f"{f}: doc_id {rec.get('doc_id')} not allowlisted"
                    assert MARKER not in json.dumps(rec), f"{f}: excluded path in record"
            else:
                assert MARKER.encode() not in f.read_bytes(), f"{f}: excluded path present"


def test_index_chunk_lists_are_allowlisted():
    allowed = _allowed_doc_ids()
    for name in ("bm25.json", "embeddings.json"):
        path = ROOT / "indexes" / name
        if path.exists():
            for chunk_id in json.loads(path.read_text())["chunk_ids"]:
                assert chunk_id.split(":")[0] in allowed, chunk_id
