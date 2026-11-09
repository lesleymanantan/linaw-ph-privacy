import csv

from ph_privacy_guide import catalogue
from ph_privacy_guide.config import (DRAFT_LABEL, IRR_AMENDED_LABEL, LISTED_BASIS, LISTED_LABEL, LISTED_VARIANTS, RA_STATUS_TEXT, ROOT,
                                     STATUS_LISTED)

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
    assert rows["NPC_Circular_16-03_Breach_Management"]["status"] == STATUS_LISTED
    assert rows["NPC_Circular_16-03_Breach_Management"]["clarified_by"] == "NPC_Advisory_2026-02_DBNMS_Clarification"
    for r in rows.values():
        if r["in_corpus"] == "no":
            assert r["file_path"] == ""


def test_only_confirmed_statuses_are_set():
    repealed = {"NPC_Circular_17-01", "NPC_Circular_16-01", "NPC_Circular_16-02", "NPC_Advisory_2020-04"}
    for r in catalogue.load():
        if r["collection"] == "drafts":
            assert r["status"] == "draft" and r["authority"] == "draft"
            assert DRAFT_LABEL.split(",")[0] in r["notes"].lower()
        elif r["instrument_key"] in LISTED or r["doc_id"] in LISTED_VARIANTS:
            assert r["status"] == STATUS_LISTED, r["doc_id"]
        elif r["doc_id"] in repealed:
            assert r["status"] == "repealed", r["doc_id"]
        elif r["doc_id"] == "IRR_RA10173":
            assert r["status"] == "amended"
        else:
            assert r["status"] == "unverified", r["doc_id"]


def test_added_repealed_rows():
    rows = {r["doc_id"]: r for r in catalogue.load()}
    assert rows["NPC_Circular_16-02"]["status"] == "repealed"
    assert "2020-03 s.20" in rows["NPC_Circular_16-02"]["status_basis"]
    assert rows["NPC_Circular_16-02"]["replaced_by"] == "NPC_Circular_2020-03_Data_Sharing_Agreements"
    assert rows["NPC_Advisory_2020-04"]["status"] == "repealed"
    assert "advisories page note" in rows["NPC_Advisory_2020-04"]["status_basis"]
    assert rows["NPC_Advisory_2020-04"]["in_corpus"] == "no"


def test_the_plain_listed_wording_applies_to_those_19_only():
    rows = catalogue.load()
    listed = [r for r in rows if r["status"] == STATUS_LISTED and r["doc_id"] not in LISTED_VARIANTS]
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


def test_only_the_draft_label_may_say_in_force_and_no_status_says_supplement():
    rows = catalogue.load()
    for key in ("NPC_Circular_16-03_Breach_Management", "NPC_Circular_2022-04_Registration", "NPC_Circular_2023-06_Security",
                "NPC_Circular_2022-04_Annex1", "RA10173_DPA_2012", "IRR_RA10173"):
        row = next(r for r in rows if r["doc_id"] == key)
        original = row["status_label"]
        row["status_label"] = "in force"
        assert any(key in e and "in force" in e for e in catalogue.validate(rows)), key
        row["status_label"] = "supplemented by another"
        assert any(key in e and "supplements" in e for e in catalogue.validate(rows)), key
        row["status_label"] = original
    assert catalogue.validate(rows) == []
    rows[0]["status"] = "in_force"
    assert any("bad status" in e for e in catalogue.validate(rows))


def test_owner_wording_for_the_circulars_and_the_acts():
    rows = {r["instrument_key"]: r for r in catalogue.load()}
    assert rows["NPC_Circular_16-03"]["status_label"] == (
        "Listed by NPC, no repeal noted. Advisory 2026-02 (2026-05) gives clarifications for requests under it, "
        "which shows it is still applied. Not independently verified.")
    assert rows["NPC_Circular_2022-04"]["status_basis"] == LISTED_BASIS + "; supersedes Circular 17-01 (s.40)"
    assert rows["NPC_Circular_2023-06"]["status_basis"] == LISTED_BASIS + "; expressly repeals Circular 16-01 (s.39)"
    assert rows["NPC_Circular_2022-04"]["status_label"] == rows["NPC_Circular_2023-06"]["status_label"] == LISTED_LABEL
    assert all("project owner" not in rows[k]["status_basis"].lower() for k in ("NPC_Circular_2022-04", "NPC_Circular_2023-06"))
    assert rows["RA10173"]["status"] == "unverified" and rows["RA10173"]["status_label"] == RA_STATUS_TEXT
    irr = rows["IRR_RA10173"]
    assert irr["status_label"] == IRR_AMENDED_LABEL and "2020-03" in irr["status_basis"]
    assert "later annotated copy" in irr["notes"]


def test_annex_follows_its_circular_and_the_rest_stay_not_verified():
    rows = {r["instrument_key"]: r for r in catalogue.load()}
    annex = rows["NPC_Circular_2022-04_Annex1"]
    assert annex["status_label"] == rows["NPC_Circular_2022-04"]["status_label"] and annex["status"] == STATUS_LISTED
    assert annex["status_basis"].startswith("Annex of NPC Circular 2022-04")
    for key in ("NPC_Advisory_2017-03", "NPC_Toolkit_Ch2"):
        assert rows[key]["status"] == "unverified" and rows[key]["status_label"] == "not verified", key
    for key in ("NPC_Circular_17-01", "NPC_Circular_16-01", "NPC_Circular_16-02", "NPC_Advisory_2020-04"):
        assert rows[key]["status"] == "repealed" and rows[key]["status_label"] == "repealed"


# Not on the NPC links list. Supplied by the project owner, who downloaded each on 2026-11-09 and found it identical
# (same sha256) to the saved copy in data/raw/.
OWNER_CHECKED_URLS = {
    "RA10173_DPA_2012": "https://privacy.gov.ph/wp-content/uploads/2024/06/DPA-of-2012_1.pdf",
    "IRR_RA10173": "https://privacy.gov.ph/wp-content/uploads/2023/06/IRR_RA-10173-as-amended.pdf",
    "DRAFT_Updated_PIA_Guidelines_Circular":
        "https://privacy.gov.ph/wp-content/uploads/2026/08/For-Public-Consultation-Draft-Circular-Updated-PIA-Guidelines.pdf",
    "NPC_Toolkit_Ch2_PIA_0618": "https://privacy.gov.ph/wp-content/uploads/2022/01/NPC_PIA_0618.pdf",
}


def test_source_urls_are_copied_exactly_from_the_npc_links_list_or_the_owner_checked_list():
    with open(ROOT / "data" / "reference" / "npc_page_links_5Nov.csv", newline="", encoding="utf-8-sig") as f:
        listed = {row["url"] for row in csv.DictReader(f)}
    rows = catalogue.load()
    assert all(r["source_url"] != "TBS" for r in rows) and len({r["source_url"] for r in rows}) == len(rows) == 32
    for r in rows:
        if r["doc_id"] in OWNER_CHECKED_URLS:
            assert r["source_url"] == OWNER_CHECKED_URLS[r["doc_id"]] and r["retrieved_on"] == "2026-11-09", r["doc_id"]
        else:
            assert r["source_url"] in listed and r["retrieved_on"] in ("TBS", ""), r["doc_id"]
