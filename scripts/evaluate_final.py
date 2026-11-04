#!/usr/bin/env python3
"""Run the test split, once. Needs --final, and a committed, matching eval/questions/test.sha256."""
import argparse
import sys

from ph_privacy_guide.evaluate.metrics import run_final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", help="confirm that this is the one final run")
    return run_final(parser.parse_args().final)


if __name__ == "__main__":
    sys.exit(main())
