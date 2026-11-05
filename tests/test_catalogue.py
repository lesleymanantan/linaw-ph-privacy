from ph_privacy_guide import catalogue
from ph_privacy_guide.config import DRAFT_LABEL, LISTED_BASIS, LISTED_LABEL, STATUS_LISTED

LISTED = {
    "NPC_Circular_2020-03", "NPC_Circular_2022-01", "NPC_Circular_2023-04", "NPC_Circular_2023-07", "NPC_Circular_2024-02",
    "NPC_Advisory_2017-01", "NPC_Advisory_2021-01", "NPC_Advisory_2021-02", "NPC_Advisory_2023-01", "NPC_Advisory_2024-01",
    "NPC_Advisory_2024-02", "NPC_Advisory_2024-03", "NPC_Advisory_2024-04", "NPC_Advisory_2025-01", "NPC_Advisory_2025-02",
    "NPC_Advisory_2026-01", "NPC_Advisory_2026-02", "NPC_Advisory_2026-03", "NPC-IC_Joint_Advisory_2025-001",
}


def test_catalogue_validates():
    assert catalogue.validate(catalogue.load()) == []


def test_known_statuses():
    rows = {r["doc_id"]: r for r in catalogue.load()}
    assert rows["NPC_Circular_17-01"]["status"] == "repealed"
    assert rows["NPC_Circular_17-01"]["replaced_by"] == "NPC_Circular_2022-04_Registration"
    assert rows["NPC_Circular_16-01"]["status"] == "repealed"
    assert rows["NPC_Circular_16-01"]["replaced_by"] == "NPC_Circular_2023-06_Security"
    assert rows["NPC_Circular_16-03_Breach_Management"]["status"] == "in_force"
    assert rows["NPC_Circular_16-03_Breach_Management"]["supplemented_by"] == "NPC_Advisory_2026-02_DBNMS_Clarification"
    for r in rows.values():
        if r["in_corpus"] == "no":
            assert r["file_path"] == ""


def test_only_confirmed_statuses_are_set():
    confirmed = {"NPC_Circular_17-01", "NPC_Circular_16-01", "NPC_Circular_16-02", "NPC_Advisory_2020-04",
                 "NPC_Circular_16-03_Breach_Management", "NPC_Circular_2022-04_Registration", "NPC_Circular_2023-06_Security"}
    for r in catalogue.load():
        if r["collection"] == "drafts":
            assert r["status"] == "draft" and r["authority"] == "draft"
            assert DRAFT_LABEL.split(",")[0] in r["notes"].lower()
        elif r["instrument_key"] in LISTED:
            assert r["status"] == STATUS_LISTED, r["doc_id"]
        elif r["doc_id"] not in confirmed:
            assert r["status"] == "unverified", r["doc_id"]


def test_added_repealed_rows():
    rows = {r["doc_id"]: r for r in catalogue.load()}
    assert rows["NPC_Circular_16-02"]["status"] == "repealed"
    assert "2020-03 s.20" in rows["NPC_Circular_16-02"]["status_basis"]
    assert rows["NPC_Circular_16-02"]["replaced_by"] == "NPC_Circular_2020-03_Data_Sharing_Agreements"
    assert rows["NPC_Advisory_2020-04"]["status"] == "repealed"
    assert "advisories page note" in rows["NPC_Advisory_2020-04"]["status_basis"]
    assert rows["NPC_Advisory_2020-04"]["in_corpus"] == "no"


def test_the_listed_status_applies_to_those_19_only_with_the_exact_wording():
    rows = catalogue.load()
    listed = [r for r in rows if r["status"] == STATUS_LISTED]
    assert {r["instrument_key"] for r in listed} == LISTED and len(listed) == 19
    for r in listed:
        assert r["status_basis"] == LISTED_BASIS and r["status_label"] == LISTED_LABEL
        assert r["authority"] == "rule" or r["authority"] == "guidance"


def test_listed_never_claims_current_or_in_force():
    assert "listed as current" not in LISTED_LABEL.lower() + LISTED_BASIS.lower()
    assert "in force" not in LISTED_LABEL.lower() + LISTED_BASIS.lower()
    rows = catalogue.load()
    good = [r for r in rows if r["status"] == STATUS_LISTED][0]
    assert catalogue.validate(rows) == []
    good["status_label"] = "Listed as current by NPC"
    assert any("listed as current" in e or "exact basis" in e for e in catalogue.validate(rows))


def test_open_documents_stay_not_verified_with_their_evidence_in_notes():
    rows = {r["instrument_key"]: r for r in catalogue.load()}
    for key in ("RA10173", "IRR_RA10173", "NPC_Advisory_2017-03", "NPC_Circular_2022-04_Annex1", "NPC_Toolkit_Ch2"):
        assert rows[key]["status"] == "unverified" and rows[key]["status_label"] == "not verified", key
    assert "2020-03" in rows["IRR_RA10173"]["notes"]
    assert "s.16" in rows["NPC_Advisory_2017-03"]["notes"]


def test_step_3_statuses():
    rows = {r["instrument_key"]: r for r in catalogue.load()}
    assert rows["NPC_Circular_16-03"]["status_label"] == "in force, supplemented by Advisory 2026-02"
    assert rows["NPC_Circular_2022-04"]["status_label"] == "in force"
    assert rows["NPC_Circular_2023-06"]["status_label"] == "in force"
    for key in ("NPC_Circular_17-01", "NPC_Circular_16-01", "NPC_Circular_16-02", "NPC_Advisory_2020-04"):
        assert rows[key]["status"] == "repealed" and rows[key]["status_label"] == "repealed"
