"""Project paths and the collection allowlist.

data/raw/ is read ONLY through ALLOWED_COLLECTIONS. data/raw/excluded/ must never be
opened, globbed or listed. Never glob data/raw/ recursively.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
CATALOGUE = ROOT / "catalogue" / "catalogue.csv"
REPORTS = ROOT / "reports"

# collection folder -> default authority hint (the catalogue is authoritative)
ALLOWED_COLLECTIONS = ("privacy-law", "npc-guidance", "drafts", "npc-toolkit")
EXCLUDED_DIRNAME = "excluded"

DRAFT_LABEL = "draft, not in force"


def allowed_pdfs() -> list[Path]:
    """List PDFs in the allowlisted collection folders only (non-recursive)."""
    out: list[Path] = []
    for coll in ALLOWED_COLLECTIONS:
        folder = RAW / coll
        if not folder.is_dir():
            continue
        out.extend(sorted(p for p in folder.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()))
    for p in out:
        assert EXCLUDED_DIRNAME not in p.relative_to(RAW).parts
    return out
