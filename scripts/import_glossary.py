#!/usr/bin/env python3
"""Import reviewed Filipino terms into data/glossary/en_fil_terms.csv. Usage: import_glossary.py FILE.csv

Input columns: en_term, fil_term, fil_variants, fil_source, fil_reviewer. Columns starting with "ref_" are ignored.
fil_variants are separated by ";". en_term matches existing rows ignoring case. Rows with an empty fil_term are
skipped. Unmatched rows are printed and not written. If any row is invalid, nothing is written. Values are copied
as given; this script never creates or translates one.
"""
import argparse
import sys
from pathlib import Path

from ph_privacy_guide.glossary import import_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    report = import_csv(parser.parse_args().csv)
    if report.skipped:
        print(f"Skipped {len(report.skipped)} rows with no fil_term.")
    if report.unmatched:
        print(f"{len(report.unmatched)} unmatched rows, not written:")
        print("\n".join(f"- {row}" for row in report.unmatched))
    if report.errors:
        print(f"{len(report.errors)} problems; nothing was written:")
        print("\n".join(f"- {error}" for error in report.errors))
        return 1
    if not report.written:
        print("No rows to import; nothing was written.")
        return 0
    print(f"Wrote {len(report.imported)} rows, replacing existing values on {len(report.replaced)}.")
    if report.replaced:
        print("Replaced: " + "; ".join(report.replaced))
    return 0


if __name__ == "__main__":
    sys.exit(main())
