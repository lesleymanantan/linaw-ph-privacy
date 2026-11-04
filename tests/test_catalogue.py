from ph_privacy_guide import catalogue
from ph_privacy_guide.config import DRAFT_LABEL


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
    confirmed = {"NPC_Circular_17-01", "NPC_Circular_16-01", "NPC_Circular_16-03_Breach_Management"}
    for r in catalogue.load():
        if r["collection"] == "drafts":
            assert r["status"] == "draft" and r["authority"] == "draft"
            assert DRAFT_LABEL.split(",")[0] in r["notes"].lower()
        elif r["doc_id"] not in confirmed:
            assert r["status"] == "unverified", r["doc_id"]
