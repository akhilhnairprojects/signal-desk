"""Weekly sync (Friday nights, per the automation schedule).

Aggregates the week's activity into the main dashboard:
  1. Pulls the current state of every store table (notes, KB, custom
     accounts, news) - the database is the source of truth, and this run
     also refreshes the CSV mirrors in the repo as a versioned backup.
  2. Re-runs the full scoring pipeline.
  3. Writes results/weekly_digest.json, which the home page displays.

Usage: python scripts/weekly_sync.py
Scheduled by .github/workflows/weekly.yml.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import build_dataset, config, news, store


def _recent(df: pd.DataFrame, date_col: str, days: int = 7) -> int:
    if df.empty:
        return 0
    dates = pd.to_datetime(df[date_col], errors="coerce", utc=True,
                           format="mixed")
    cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=days)
    return int((dates >= cutoff).sum())


def main() -> None:
    # 1. Sync store -> CSV mirrors (store.load already writes nothing; the
    #    mirrors update on writes, so here we just force-load and re-save
    #    to capture anything written directly to the database).
    for table in store.TABLES:
        store._csv_save(table, store.load(table))
    print("Store tables mirrored to data/ (versioned backup).")

    # 2. Full pipeline.
    df, notes, meta = build_dataset()
    kb = store.load("kb_articles")
    signals = news.load_signals()

    config.RESULTS_DIR.mkdir(exist_ok=True)
    export_cols = [
        "account", "ticker", "industry", "sub_industry", "source",
        *config.SIGNAL_WEIGHTS,
        "base_score", "note_count", "kb_count", "note_adj", "kb_adj",
        "news_adj", "adjusted_score", "tier", "tier_action", "segment",
        "lookalikes",
    ]
    (df[export_cols].sort_values("adjusted_score", ascending=False)
       .to_csv(config.RESULTS_DIR / "accounts_scored.csv", index=False))

    # 3. Digest.
    covered = int((signals["news_score"] > 0).sum()) if not signals.empty else 0
    top_news = (signals.sort_values("news_score", ascending=False).head(5)
                [["account", "news_score"]].to_dict("records")
                if covered else [])
    df = df.assign(delta=(df["adjusted_score"] - df["base_score"]).round(1))
    moved = df[df["delta"] != 0]
    movers = (moved.reindex(moved["delta"].abs()
                            .sort_values(ascending=False).index)
              .head(5)[["account", "delta"]].to_dict("records"))

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "accounts": len(df),
        "notes_last_7d": _recent(notes, "date"),
        "kb_edits_last_7d": _recent(kb, "updated_at"),
        "custom_accounts": int((df["source"] == "custom").sum()),
        "news_coverage": covered,
        "top_news": top_news,
        "top_movers": movers,
        "tier_counts": df["tier"].value_counts().to_dict(),
        "storage_backend": meta.get("storage_backend", "csv"),
    }
    (config.RESULTS_DIR / "weekly_digest.json").write_text(
        json.dumps(digest, indent=2))

    print(f"Weekly digest written: {digest['notes_last_7d']} notes and "
          f"{digest['kb_edits_last_7d']} KB edits this week, "
          f"{digest['custom_accounts']} custom accounts, "
          f"{covered} accounts with news coverage.")


if __name__ == "__main__":
    main()
