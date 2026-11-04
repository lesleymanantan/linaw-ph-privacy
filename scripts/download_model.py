#!/usr/bin/env python3
"""DEV ONLY. Download the approved embedding model once, at a pinned revision.

Usage: .venv/bin/python scripts/download_model.py

Never imported at runtime. Downloads only the files the tool needs, verifies LFS hashes against the
repository listing, stores everything under models/ (gitignored) and logs the model in MODELS.md.
Refuses to run if the model is already present.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

from ph_privacy_guide.config import EMBEDDING_MODEL_DIR, EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_REVISION, ROOT

FILES = ["onnx/model.onnx", "onnx/tokenizer.json", "onnx/config.json", "1_Pooling/config.json", "README.md"]
BASE = f"https://huggingface.co/{EMBEDDING_MODEL_NAME}"
TMP = ROOT / ".tools" / "tmp"
MANIFEST = EMBEDDING_MODEL_DIR / "manifest.json"


def curl(url: str, dest) -> None:
    subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "1800",
                    "--output", str(dest), url], check=True)


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def card_field(front_matter: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(\S.*)$", front_matter, re.M)
    return m.group(1).strip() if m else ""


def main() -> None:
    if MANIFEST.exists():
        sys.exit(f"Already downloaded: {MANIFEST}. This script runs once.")
    TMP.mkdir(parents=True, exist_ok=True)
    listing = TMP / "model_listing.json"
    curl(f"https://huggingface.co/api/models/{EMBEDDING_MODEL_NAME}/tree/{EMBEDDING_MODEL_REVISION}?recursive=true", listing)
    tree = {e["path"]: e for e in json.loads(listing.read_text()) if e["type"] == "file"}

    files = {}
    for rel in FILES:
        dest = EMBEDDING_MODEL_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = TMP / (rel.replace("/", "_") + ".part")
        curl(f"{BASE}/resolve/{EMBEDDING_MODEL_REVISION}/{rel}", part)
        size, digest = part.stat().st_size, sha256(part)
        expected = tree[rel]
        if size != expected["size"]:
            sys.exit(f"{rel}: size {size}, repository says {expected['size']}")
        oid = (expected.get("lfs") or {}).get("oid")
        if oid and oid != digest:
            sys.exit(f"{rel}: sha256 {digest}, repository says {oid}")
        os.replace(part, dest)
        files[rel] = {"bytes": size, "sha256": digest}
        print(f"{rel}: {size:,} bytes, sha256 {digest[:12]}")

    card = (EMBEDDING_MODEL_DIR / "README.md").read_text()
    front = card.split("---", 2)[1]
    block = re.search(r"^language:\n((?:\s*-\s*\S+\n)+)", front, re.M)
    languages = re.findall(r"-\s*(\S+)", block.group(1)) if block else []
    total = sum(f["bytes"] for f in files.values())
    today = datetime.date.today().isoformat()
    manifest = {
        "name": EMBEDDING_MODEL_NAME, "revision": EMBEDDING_MODEL_REVISION, "source_url": BASE,
        "licence_from_card": card_field(front, "license"), "tagalog_in_card_languages": "tl" in languages,
        "card_language_count": len(languages), "downloaded": today, "total_bytes": total, "files": files,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))

    log = ROOT / "MODELS.md"
    text = log.read_text().replace("| _none yet_ | | | | | | | |\n", "")
    row = (f"| {EMBEDDING_MODEL_NAME} | `{EMBEDDING_MODEL_REVISION}` | {total / 1_000_000:.1f} MB "
           f"({len(files)} files; model.onnx {files['onnx/model.onnx']['bytes'] / 1_000_000:.1f} MB) | "
           f"{manifest['licence_from_card']} | {BASE} | {today} | "
           f"`{files['onnx/model.onnx']['sha256']}` | Passage and query embeddings for hybrid retrieval |\n")
    log.write_text(text + row)
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
