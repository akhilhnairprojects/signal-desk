"""Refresh competitor headlines (scheduled nightly in news.yml).

Usage: python scripts/collect_competitor_news.py [--limit 3]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import competitors, config


def main(limit: int | None = None) -> None:
    n = limit or len(config.COMPETITORS)
    print(f"Collecting news for {n} competitors...")
    heads = competitors.collect_all(limit=limit)
    print(f"{len(heads)} competitor headlines on file.")


if __name__ == "__main__":
    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
    main(lim)
