"""Command-line search. Usage: python -m ph_privacy_guide.app.cli "search terms" [-k 5]"""
from __future__ import annotations

import argparse

from ph_privacy_guide.offline import enforce_offline


def main(argv: list[str] | None = None) -> None:
    enforce_offline()
    from ph_privacy_guide.answer.format import format_result
    from ph_privacy_guide.config import INCLUDE_DRAFT_ANNEX, RESULTS_SHOWN
    from ph_privacy_guide.retrieve.search import Searcher

    parser = argparse.ArgumentParser(description="Find passages of Philippine data privacy law. Not legal advice.")
    parser.add_argument("query")
    parser.add_argument("-k", type=int, default=RESULTS_SHOWN, help=f"passages to show (default {RESULTS_SHOWN})")
    parser.add_argument("--include-draft-annex", action="store_true", default=INCLUDE_DRAFT_ANNEX,
                        help="also search Annex A of the draft circular (draft, not in force)")
    args = parser.parse_args(argv)
    result = Searcher().search(args.query, k=args.k, include_draft_annex=args.include_draft_annex)
    print(format_result(args.query, result))


if __name__ == "__main__":
    main()
