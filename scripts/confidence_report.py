#!/usr/bin/env python3
"""Show what each "not sure" threshold would do on the dev split, per language. Sets nothing.

Takes no arguments: it cannot be pointed at any other file.
"""
import sys

from ph_privacy_guide.evaluate.metrics import confidence_report

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit("confidence_report.py takes no arguments. It runs on eval/questions/dev.jsonl only.")
    sys.exit(confidence_report())
