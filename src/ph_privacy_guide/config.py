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


# Status for documents on the NPC advisories and circulars page. That page also lists repealed Circulars
# 17-01 and 16-01 with no repeal note, so being listed does not prove a document is current.
STATUS_LISTED = "listed_no_repeal"
LISTED_LABEL = "Listed by NPC, no repeal noted; not independently verified"
LISTED_BASIS = ("Listed on the NPC advisories and circulars page (page dated 2026-09-21; retrieved 2026-10-25); "
                "page marks no repeal; none found in the corpus; not independently verified")

# Listed documents whose wording adds something to the plain label or basis. Exact text, checked by the catalogue.
LISTED_VARIANTS = {
    "NPC_Circular_16-03_Breach_Management": (
        "Listed by NPC, no repeal noted. Advisory 2026-02 (2026-05) gives clarifications for requests under it, "
        "which shows it is still applied. Not independently verified.",
        LISTED_BASIS + "; Advisory 2026-02 (2026-05) gives clarifications for requests under it (s.2), "
        "which shows it is still applied"),
    "NPC_Circular_2022-04_Registration": (LISTED_LABEL, LISTED_BASIS + "; supersedes Circular 17-01 (s.40)"),
    "NPC_Circular_2023-06_Security": (LISTED_LABEL, LISTED_BASIS + "; expressly repeals Circular 16-01 (s.39)"),
    "NPC_Circular_2022-04_Annex1": (
        LISTED_LABEL, "Annex of NPC Circular 2022-04, which refers to it in s.6 (see Annex 1); status follows the circular: "
        + LISTED_BASIS),
}
RA_STATUS_TEXT = "Downloaded from NPC's DPA and IRR page; no amendment found in the corpus; not independently verified."
IRR_AMENDED_LABEL = "Amended by NPC Circular 2020-03 (per NPC annotations in the text); otherwise not independently verified"

# Warnings on every chunk of a document.
DOCUMENT_WARNINGS = {
    "NPC_Advisory_2017-03_PIA": ("A draft circular (not in force) would supersede this advisory if adopted. "
                                 "Check the NPC site for the current position."),
    "NPC_Circular_2022-04_Annex1": "Annex of NPC Circular 2022-04. Its status follows the circular.",
}

# Warnings quoting an annotation printed in the text. The quote must be in that section, or the build stops.
# (doc_id, section, subsection prefix; "" covers the whole section) -> (what the annotation says, quote, doc_id it points to).
TEXT_ANNOTATION_WARNINGS = {
    ("IRR_RA10173", "3", "(f)"): (
        "Amended", "(as amended by NPC Circular No. 2020-03)", "NPC_Circular_2020-03_Data_Sharing_Agreements"),
    ("IRR_RA10173", "20", ""): (
        "Superseded", "(The entire Section 20 is superseded by NPC Circular No. 2020-03)",
        "NPC_Circular_2020-03_Data_Sharing_Agreements"),
}

# Cleaning rules: text removed from chunks only. Raw PDFs, page text and section records keep it.
# Each rule matches one document, one section and one exact block of lines, and every removal is logged.
CHUNK_CLEANING_RULES = [{
    "rule": "advisory-2026-02-running-header",
    "doc_id": "NPC_Advisory_2026-02_DBNMS_Clarification",
    "section": "2",
    "pattern": (r"^NPC Advisory No\. 2026-02 – Clarification on the\n"
                r"Submission of Personal Data Breach Notification\n"
                r"through Data Breach Notification Management\n"
                r"System\n"
                r"Page \d+ of \d+\n"),
}]

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

# Fixed result layout. Not tuned on any questions.
# The main block holds statutes, rules and guidance. Drafts and the 16-03 Summary never enter it: each
# has its own labelled block below, with at most SIDE_BLOCK_MAX passages, shown only if its fused score
# reaches the score of the last passage in the main block (the same relevance bar).
MAIN_RESULTS = 3
SIDE_BLOCK_MAX = 1
BLOCK_MAIN = "main"
BLOCK_PENDING = "pending"
BLOCK_SUMMARY = "summary"
BLOCK_HEADINGS = {BLOCK_PENDING: "Pending change: draft, not law", BLOCK_SUMMARY: SUMMARY_LABEL}


def result_block(kind: str, status: str) -> str:
    if status == "draft":
        return BLOCK_PENDING
    if kind == "summary":
        return BLOCK_SUMMARY
    return BLOCK_MAIN


# Hybrid retrieval: reciprocal rank fusion with the standard default and equal weights.
RRF_K = 60
RRF_WEIGHT_BM25 = 1.0
RRF_WEIGHT_EMBEDDING = 1.0

# "Not sure" comes from a score-based confidence (retrieve/confidence.py). Equal weights are a default,
# not a finding. The threshold stays None until the dev set exists, and may be set only from dev.
CONFIDENCE_WEIGHTS = {"top_fused": 1.0, "margin": 1.0, "agreement": 1.0, "top_cosine": 1.0, "term_coverage": 1.0}
NOT_SURE_CONFIDENCE_THRESHOLD = None

# Embedding model, approved by the project owner. Loaded from local files only.
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
EMBEDDING_MODEL_DIR = ROOT / "models" / "multilingual-e5-small"
EMBEDDING_MAX_TOKENS = 512
EMBEDDING_QUERY_PREFIX = "query: "  # the model card requires these prefixes
EMBEDDING_PASSAGE_PREFIX = "passage: "
EMBEDDING_THREADS = 0  # 0 lets onnxruntime decide
# Token-based splitting of chunks too long for the model. About one sentence of overlap.
MAX_OVERLAP_TOKENS = 60
TOKEN_SAFETY_MARGIN = 8
KEYWORD_ONLY_NOTE = "Keyword-searchable beyond the limit: the embedding model reads only the first 512 tokens."

# Local web page.
WEB_HOST = "127.0.0.1"
WEB_PORT = 8765
CONTACT_URL = "https://privacy.gov.ph/contactus/"
