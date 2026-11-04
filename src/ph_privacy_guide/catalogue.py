"""Catalogue loading, validation and sha256 filling.

Usage:
  python -m ph_privacy_guide.catalogue --fill-hashes   # compute sha256 for in-corpus rows
  python -m ph_privacy_guide.catalogue                 # validate only
"""
from __future__ import annotations

import csv
import hashlib
import sys

from ph_privacy_guide.config import CATALOGUE, EXCLUDED_DIRNAME, ROOT, allowed_pdfs

FIELDS = [
    "doc_id", "short_cite", "title", "type", "issuer", "collection", "authority", "status",
    "status_basis", "replaced_by", "supersedes", "supplemented_by", "parent_doc_id",
    "date_issued", "date_effective", "version", "in_corpus", "file_path", "sha256",
    "source_url", "retrieved_on", "notes",
]
AUTHORITIES = {"statute", "rule", "guidance", "policy", "draft"}
STATUSES = {"in_force", "repealed", "amended", "draft", "unverified"}
TYPES = {"statute", "irr", "circular", "annex", "advisory", "joint_advisory", "toolkit", "draft_circular"}


def load() -> list[dict]:
    with open(CATALOGUE, newline="") as f:
        return list(csv.DictReader(f))


def save(rows: list[dict]) -> None:
    with open(CATALOGUE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def validate(rows: list[dict]) -> list[str]:
    errs: list[str] = []
    ids = [r["doc_id"] for r in rows]
    if len(ids) != len(set(ids)):
        errs.append("duplicate doc_id")
    idset = set(ids)
    corpus_files = {str(p.relative_to(ROOT)) for p in allowed_pdfs()}
    listed_files = set()
    for r in rows:
        d = r["doc_id"]
        if list(r.keys()) != FIELDS:
            errs.append(f"{d}: columns differ from schema")
        if EXCLUDED_DIRNAME in r["file_path"].split("/"):
            errs.append(f"{d}: excluded path in catalogue")
        if r["authority"] not in AUTHORITIES:
            errs.append(f"{d}: bad authority {r['authority']!r}")
        if r["status"] not in STATUSES:
            errs.append(f"{d}: bad status {r['status']!r}")
        if r["type"] not in TYPES:
            errs.append(f"{d}: bad type {r['type']!r}")
        if r["status"] not in ("unverified", "draft") and not r["status_basis"]:
            errs.append(f"{d}: status {r['status']} needs status_basis")
        if r["status"] == "repealed" and not r["replaced_by"]:
            errs.append(f"{d}: repealed without replaced_by")
        if (r["collection"] == "drafts") != (r["status"] == "draft" and r["authority"] == "draft"):
            errs.append(f"{d}: drafts collection must have status=draft and authority=draft")
        for ref_field in ("replaced_by", "supplemented_by", "parent_doc_id"):
            for ref in filter(None, r[ref_field].split(";")):
                if ref not in idset:
                    errs.append(f"{d}: {ref_field} -> unknown doc_id {ref}")
        if r["in_corpus"] == "yes":
            listed_files.add(r["file_path"])
            if r["file_path"] not in corpus_files:
                errs.append(f"{d}: file_path not in allowlisted corpus")
            elif r["sha256"] and r["sha256"] != sha256(ROOT / r["file_path"]):
                errs.append(f"{d}: sha256 mismatch")
            if not r["sha256"]:
                errs.append(f"{d}: missing sha256")
        elif r["in_corpus"] == "no":
            if r["file_path"] or r["sha256"]:
                errs.append(f"{d}: not in corpus but has file_path/sha256")
        else:
            errs.append(f"{d}: in_corpus must be yes/no")
    for missing in sorted(corpus_files - listed_files):
        errs.append(f"corpus file without catalogue row: {missing}")
    return errs


def write_sources(rows: list[dict]) -> None:
    """Regenerate SOURCES.md from the catalogue (the catalogue is the source of truth)."""
    lines = [
        "# SOURCES.md",
        "",
        "Provenance of every legal text. **Generated from `catalogue/catalogue.csv`** by",
        "`python -m ph_privacy_guide.catalogue --sources`; edit the catalogue, not this file.",
        "`TBS` = to be supplied. Status `unverified` = not yet confirmed from a cited provision.",
        "",
        "| doc_id | Citation | Status | Status basis | Version | Source URL | Retrieved | sha256 (first 12) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        basis = r["status_basis"].replace("|", "/") or "—"
        lines.append(f"| {r['doc_id']} | {r['short_cite']} | {r['status']} | {basis} | {r['version'] or '—'} | "
                     f"{r['source_url'] or '—'} | {r['retrieved_on'] or '—'} | {r['sha256'][:12] or '—'} |")
    (ROOT / "SOURCES.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    rows = load()
    if "--fill-hashes" in sys.argv:
        for r in rows:
            if r["in_corpus"] == "yes":
                r["sha256"] = sha256(ROOT / r["file_path"])
        save(rows)
    if "--sources" in sys.argv:
        write_sources(rows)
    errs = validate(rows)
    print(f"{len(rows)} rows; {sum(r['in_corpus'] == 'yes' for r in rows)} in corpus")
    for e in errs:
        print("ERROR:", e)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
