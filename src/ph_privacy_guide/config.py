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


# Labels shown wherever these texts appear.
ANNOTATION_LABEL = "NPC annotation"
SUMMARY_LABEL = "NPC summary, not the rule text"
TOOLKIT_LABEL = "educational guidance; may predate later advisories"

# Config switch: the draft's Annex A is not searchable unless this is True (or --include-draft-annex).
INCLUDE_DRAFT_ANNEX = False

# Which record kinds are searchable by default. Footnotes are shown under their section instead.
SEARCHABLE_KINDS = {"section", "part", "annex", "summary"}

# IRR footnotes citing these repealed circulars add a warning to the linked IRR chunk.
# Pattern -> (repealed citation, replacing doc_id, the provision that does it).
REPEALED_FOOTNOTE_WARNINGS = {
    r"Circular\s+(?:No\.\s*)?(?:20)?17\s*-\s*01": (
        "NPC Circular 17-01", "NPC_Circular_2022-04_Registration", "s.40 supersedes 17-01"),
    r"Circular\s+(?:No\.\s*)?(?:20)?16\s*-\s*01": (
        "NPC Circular 16-01", "NPC_Circular_2023-06_Security", "s.39 repeals 16-01"),
}

# Fixed result ordering. Not tuned on any questions. Results are chosen by relevance, then the
# passages shown are ordered by tier, lowest first: rules and guidance, then the 16-03 Summary,
# then the draft.
RANK_TIER_DEFAULT = 0
RANK_TIER_SUMMARY = 1
RANK_TIER_DRAFT = 2


def rank_tier(kind: str, status: str) -> int:
    if status == "draft":
        return RANK_TIER_DRAFT
    if kind == "summary":
        return RANK_TIER_SUMMARY
    return RANK_TIER_DEFAULT


# Hybrid retrieval: reciprocal rank fusion with the standard default and equal weights.
RRF_K = 60
RRF_WEIGHT_BM25 = 1.0
RRF_WEIGHT_EMBEDDING = 1.0

# "Not sure" if the best passage shown has under this share of the search terms. Provisional:
# the threshold is to be set on the human-written dev set, and nowhere else.
NOT_SURE_MIN_TERM_COVERAGE = 0.5

# Embedding model, approved by the project owner. Loaded from local files only.
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
EMBEDDING_MODEL_DIR = ROOT / "models" / "multilingual-e5-small"
EMBEDDING_MAX_TOKENS = 512
EMBEDDING_QUERY_PREFIX = "query: "  # the model card requires these prefixes
EMBEDDING_PASSAGE_PREFIX = "passage: "
EMBEDDING_THREADS = 0  # 0 lets onnxruntime decide

# Local web page.
WEB_HOST = "127.0.0.1"
WEB_PORT = 8765
RESULTS_SHOWN = 5
CONTACT_URL = "https://privacy.gov.ph/contactus/"
