"""Collect measured signals: SEC filings + AI job postings.

Run weekly (scheduled in .github/workflows/weekly.yml) or on demand:
    python scripts/collect_measured.py [--limit 10]

Requires EDGAR_CONTACT in src/config.py to be set to your real email
(SEC's fair-use policy). Job postings cover only the companies mapped in
data/measured/hiring_sources.csv - coverage grows as you add rows.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, ingest, measured


def main(limit: int | None = None) -> None:
    if "example.com" in config.EDGAR_CONTACT:
        print("Set EDGAR_CONTACT in src/config.py to your real email first "
              "(SEC requires an identifying User-Agent). Skipping filings.")
        cik_map = None
    else:
        try:
            cik_map = measured.load_cik_map()
            print(f"CIK map loaded: {len(cik_map)} tickers.")
        except Exception as e:
            print(f"Could not load the SEC ticker map ({type(e).__name__}) "
                  "- skipping filings this run.")
            cik_map = None

    df = ingest.load_accounts()
    if limit:
        df = df.head(limit)

    filings_done = 0
    if cik_map:
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", "")).strip().upper()
            cik = cik_map.get(ticker)
            if not cik:
                continue
            count = measured.count_ai_filings(cik)
            time.sleep(0.15)                      # stay well inside SEC limits
            if count is None:
                continue
            measured.save_measurement(
                row["account"], "ai_announce", measured.scale_filings(count),
                f"SEC EDGAR: {count} AI-referencing filings "
                f"({config.MEASURED_LOOKBACK_DAYS}d)")
            filings_done += 1
        print(f"Filings measured for {filings_done} accounts.")

    sources = measured.load_hiring_sources()
    hiring_done = 0
    for _, src_row in sources.iterrows():
        count = measured.count_ai_postings(src_row["ats"],
                                           src_row["board_token"])
        if count is None:
            print(f"  {src_row['account']}: board unreachable, skipped")
            continue
        measured.save_measurement(
            src_row["account"], "ai_hiring", measured.scale_postings(count),
            f"{src_row['ats'].title()}: {count} open AI roles")
        hiring_done += 1
    print(f"Job postings measured for {hiring_done} of {len(sources)} "
          "mapped accounts. Add more mappings in "
          "data/measured/hiring_sources.csv.")
    print("Run scripts/run_pipeline.py to apply measurements to scores.")


if __name__ == "__main__":
    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
    main(lim)
