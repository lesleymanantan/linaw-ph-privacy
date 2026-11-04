#!/usr/bin/env python3
"""Freeze the test split: validate it and write its hash. Commit both files afterwards."""
import sys

from ph_privacy_guide.evaluate.metrics import file_sha256
from ph_privacy_guide.evaluate.questions import QUESTIONS_DIR, load_chunks, load_split, validate_set


def main() -> int:
    stamp = QUESTIONS_DIR / "test.sha256"
    if stamp.exists():
        print("Already frozen: eval/questions/test.sha256 exists.")
        return 1
    rows = load_split("test")
    if not rows:
        print("No test questions: eval/questions/test.jsonl is missing or empty.")
        return 1
    errors = validate_set(rows, load_chunks())
    if errors:
        print("\n".join(errors))
        return 1
    stamp.write_text(file_sha256(QUESTIONS_DIR / "test.jsonl") + "\n")
    print(f"Frozen {len(rows)} rows. Now commit eval/questions/test.jsonl and eval/questions/test.sha256 together.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
