#!/usr/bin/env python3
"""Run metrics on the dev split. Takes no arguments: it cannot be pointed at any other file."""
import sys

from ph_privacy_guide.evaluate.metrics import run_dev

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit("evaluate.py takes no arguments. It runs on eval/questions/dev.jsonl only.")
    sys.exit(run_dev())
