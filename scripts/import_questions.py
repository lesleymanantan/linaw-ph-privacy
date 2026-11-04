#!/usr/bin/env python3
"""Import human-written questions from CSV. Usage: import_questions.py FILE.csv --split dev

All rows must be valid or nothing is written. See eval/GUIDELINES.md.
"""
import argparse
import sys
from pathlib import Path

from ph_privacy_guide.evaluate.questions import SPLITS, import_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--split", required=True, choices=SPLITS)
    args = parser.parse_args()
    path, errors = import_csv(args.csv, args.split)
    if errors:
        print(f"{len(errors)} problems; nothing was written:")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
