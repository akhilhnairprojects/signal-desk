"""End-to-end pipeline runner.

Usage (from the project root):
    python scripts/run_pipeline.py

Reads the account universe and the enrichment log, rebuilds scores, tiers,
segments and lookalikes, and writes everything to results/. Run it after
changing the data, the enrichment notes, or the weights in src/config.py.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import build_dataset, config, news, segment


def main() -> None:
    prev_path = config.RESULTS_DIR / "accounts_scored.csv"
    prev = None
    if prev_path.exists():
        try:
            prev = pd.read_csv(prev_path)[["account", "tier"]]
        except Exception:
            prev = None

    df, notes, meta = build_dataset()

    config.RESULTS_DIR.mkdir(exist_ok=True)

    export_cols = [
        "account", "ticker", "industry", "sub_industry", "source",
        "measured_signals",
        *config.SIGNAL_WEIGHTS,
        "base_score", "note_count", "kb_count", "note_adj", "kb_adj",
        "news_adj", "adjusted_score",
        "tier", "tier_action", "segment", "lookalikes",
    ]
    scored = df[export_cols].sort_values("adjusted_score", ascending=False)
    scored.to_csv(config.RESULTS_DIR / "accounts_scored.csv", index=False)

    profiles = segment.segment_profiles(df)
    profiles.to_csv(config.RESULTS_DIR / "segment_profiles.csv", index=False)

    signals = news.load_signals()
    covered = int((signals["news_score"] > 0).sum()) if not signals.empty else 0

    changes = []
    if prev is not None:
        merged = prev.rename(columns={"tier": "prev_tier"}).merge(
            df[["account", "tier", "adjusted_score"]], on="account",
            how="inner")
        moved = merged[merged["prev_tier"] != merged["tier"]]
        changes = [{"account": r["account"], "from": r["prev_tier"],
                    "to": r["tier"], "score": round(r["adjusted_score"], 1)}
                   for _, r in moved.iterrows()]
    (config.RESULTS_DIR / "tier_changes.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "changes": changes,
    }, indent=2))
    if changes:
        print(f"Tier changes since last run: "
              f"{', '.join(c['account'] + ' ' + c['from'] + '->' + c['to'] for c in changes)}")

    summary = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "accounts": len(df),
        "industries": int(df["industry"].nunique()),
        "avg_score": round(float(df["adjusted_score"].mean()), 1),
        "tier_counts": df["tier"].value_counts().to_dict(),
        "enrichment_notes": len(notes),
        "custom_accounts": int((df["source"] == "custom").sum()),
        "storage_backend": meta.get("storage_backend", "csv"),
        "weights_source": meta.get("weights_source", "configured"),
        "tier_changes": len(changes),
        "news": {"accounts_with_coverage": covered,
                 "last_collected": news.last_collected(signals)},
        "segmentation": meta,
    }
    with open(config.RESULTS_DIR / "run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Scored {summary['accounts']} accounts "
          f"across {summary['industries']} industries.")
    print(f"Tiers: {summary['tier_counts']}")
    print(f"Segments: k={meta['k']} (silhouette {meta['silhouette']})")
    print(f"Enrichment notes applied: {summary['enrichment_notes']}")
    if covered:
        print(f"News signals: {covered} accounts with recent coverage")
    else:
        print("News signals: none yet (run scripts/collect_news.py)")
    print(f"Outputs written to {config.RESULTS_DIR}/")


if __name__ == "__main__":
    main()
