"""Collect live news signals for the account universe.

Usage (from the project root):
    python scripts/collect_news.py               # all 161 accounts (~3-4 min)
    python scripts/collect_news.py --limit 15    # quick test on 15 accounts

Fetches Google News RSS per account, scores AI-related momentum, and writes
data/news/news_signals.csv + data/news/headlines.csv. Run the pipeline
afterwards (or let the GitHub Action do both) to fold the signal into the
account scores.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, ingest, news


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect news signals")
    parser.add_argument("--limit", type=int, default=None,
                        help="only fetch the first N accounts (for testing)")
    parser.add_argument("--delay", type=float, default=None,
                        help="seconds between requests "
                             f"(default {config.NEWS_REQUEST_DELAY})")
    args = parser.parse_args()

    accounts = ingest.load_accounts()["account"].tolist()
    print(f"Collecting news for {args.limit or len(accounts)} of "
          f"{len(accounts)} accounts...")
    signals = news.collect_all(accounts, limit=args.limit, delay=args.delay)

    covered = int((signals["news_score"] > 0).sum())
    print(f"Done. {covered} accounts have recent AI-related coverage.")
    print(f"Signals written to {config.NEWS_SIGNALS_PATH}")
    print("Next: python scripts/run_pipeline.py")


if __name__ == "__main__":
    main()
