from ph_privacy_guide.ingest.extract import classify

NORMAL = ("SECTION 3. Definition of Terms. For the purpose of this Circular, the following terms "
          "are defined as follows: personal information controller refers to a natural or juridical person.")


def test_normal_text_ok():
    assert classify(NORMAL, 0.0)[0] == "ok"


def test_scanned_page():
    assert classify("12", 0.95)[0] == "scanned"


def test_empty_page():
    assert classify("", 0.0)[0] == "empty"


def test_cid_glyphs_suspect():
    assert classify(NORMAL + " (cid:12)(cid:45)(cid:7)", 0.0)[0] == "suspect"


def test_garbled_ocr_suspect():
    garbled = "#$%^ &*@! 9z8x7 ;;;; ~~~~ ||| 1@3# ^^^^ %%%% $$$$ !!!! &&&& **** @@@@ #### ++++ ===="
    assert classify(garbled, 0.0)[0] == "suspect"
