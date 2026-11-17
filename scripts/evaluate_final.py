#!/usr/bin/env python3
"""Run the test split, once. Needs --final, and a committed, matching eval/questions/test.sha256."""
import argparse
import sys

from ph_privacy_guide.evaluate.metrics import run_final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", help="confirm that this is the one final run")
    parser.add_argument("--allow-no-threshold", action="store_true",
                        help="run although no \"not sure\" threshold is set; recorded in the result, abstention is 0")
    args = parser.parse_args()
    return run_final(args.final, allow_no_threshold=args.allow_no_threshold)


if __name__ == "__main__":
    sys.exit(main())
