"""Publish a self-describing snapshot of the scored universe.

Writes a versioned JSON record of what the platform produced on a given run,
so the results stay readable by anyone, indefinitely, with no credentials and
no running app. Outputs land in docs/data/ and are served over GitHub Pages.

Deliberately isolated:

  - It runs build_dataset() in memory and writes ONLY under docs/data/. It
    does not touch results/, and every store write in this codebase lives in
    a mutator (append_note, collect_all, save_measurement, save_kb_article,
    delete_kb_article), none of which are on the build_dataset path.
  - CI runs it without Supabase credentials, so the pipeline reads the
    committed CSVs. That is the point: a snapshot is reproducible from the
    repository alone. Clone at any commit, run this, get that snapshot back.

Each file carries the model configuration that produced it - weights, tier
quantiles, adjustment caps - so a reader years from now can interpret the
numbers without reading the source.

Usage:
    python scripts/publish_snapshot.py                 # id defaults to YYYY-MM
    python scripts/publish_snapshot.py --id 2026-09
    python scripts/publish_snapshot.py --out some/dir
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src import build_dataset, config, scoring

SCHEMA_VERSION = 1
DEFAULT_OUT = config.ROOT / "docs" / "data"


def clean(value):
    """NaN and numpy scalars out, JSON-safe values in."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def commit_sha() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def account_records(df: pd.DataFrame) -> list[dict]:
    signals = list(config.SIGNAL_WEIGHTS)
    records = []
    for row in df.to_dict("records"):
        lookalikes = row.get("lookalikes") or ""
        records.append({
            "account": clean(row.get("account")),
            "ticker": clean(row.get("ticker")),
            "industry": clean(row.get("industry")),
            "sub_industry": clean(row.get("sub_industry")),
            "source": clean(row.get("source")),
            "signals": {s: clean(row.get(s)) for s in signals},
            "measured_signals": clean(row.get("measured_signals")),
            "base_score": clean(row.get("base_score")),
            "note_adj": clean(row.get("note_adj")),
            "kb_adj": clean(row.get("kb_adj")),
            "news_adj": clean(row.get("news_adj")),
            "adjusted_score": clean(row.get("adjusted_score")),
            "tier": clean(row.get("tier")),
            "tier_action": clean(row.get("tier_action")),
            "segment": clean(row.get("segment")),
            "lookalikes": [a for a in str(lookalikes).split("; ") if a],
        })
    return records


def build_snapshot(snapshot_id: str) -> dict:
    df, notes, meta = build_dataset()
    scores = df["adjusted_score"]

    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": commit_sha(),
        "reproduce": ("git checkout <source_commit> && "
                      "python scripts/publish_snapshot.py"),

        # Everything needed to interpret the scores below, years from now.
        "model": {
            "signal_weights": dict(config.SIGNAL_WEIGHTS),
            "signal_labels": dict(config.SIGNAL_LABELS),
            "weights_source": meta.get("weights_source", "configured"),
            "signals_percentile_ranked": True,
            "tier_quantiles": [[t, q] for t, q in config.TIER_QUANTILES],
            "tier_descriptions": dict(config.TIER_DESCRIPTIONS),
            "note_impact_points": dict(config.IMPACT_POINTS),
            "max_note_adjustment": config.MAX_ADJUSTMENT,
            "max_news_adjustment": config.MAX_NEWS_ADJUSTMENT,
            "score_definition": (
                "Percentile rank of each signal within this universe, weighted "
                "and summed, then adjusted by field notes and news momentum. "
                "A score is a position relative to the other accounts in this "
                "snapshot, not an absolute readiness rating."),
            "documentation": "docs/scoring-model.md",
        },

        "summary": {
            "accounts": int(len(df)),
            "industries": int(df["industry"].nunique()),
            "tier_counts": {k: int(v) for k, v
                            in df["tier"].value_counts().items()},
            "tier_cutoffs": {t: round(float(c), 1) for t, c
                             in scoring.tier_cutoffs(scores)},
            "score": {
                "min": round(float(scores.min()), 1),
                "max": round(float(scores.max()), 1),
                "mean": round(float(scores.mean()), 1),
                "median": round(float(scores.median()), 1),
                "sd": round(float(scores.std()), 1),
            },
            "accounts_by_industry": {k: int(v) for k, v
                                     in df["industry"].value_counts().items()},
            "field_notes": int(len(notes)),
            "accounts_with_news": int((df["news_score"] > 0).sum())
            if "news_score" in df else 0,
            "segmentation": {k: clean(v) for k, v in meta.items()
                             if k not in ("storage_backend", "weights_source")},
            "storage_backend": meta.get("storage_backend"),
        },

        "accounts": account_records(df),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def rebuild_index(out_dir: Path) -> dict:
    """Index every snapshot on disk. GitHub Pages has no directory listing,
    so this file is how a client discovers what exists."""
    entries = []
    for path in sorted((out_dir / "snapshots").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries.append({
            "id": data.get("snapshot_id", path.stem),
            "generated_at": data.get("generated_at"),
            "accounts": data.get("summary", {}).get("accounts"),
            "tier_counts": data.get("summary", {}).get("tier_counts"),
            "path": f"snapshots/{path.name}",
        })
    entries.sort(key=lambda e: e["id"])

    index = {
        "schema_version": SCHEMA_VERSION,
        "project": "Signal Desk",
        "description": ("Versioned snapshots of the scored account universe. "
                        "Each snapshot is self-describing and reproducible "
                        "from the repository at its source_commit."),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest": entries[-1]["id"] if entries else None,
        "count": len(entries),
        "snapshots": entries,
    }
    write_json(out_dir / "index.json", index)
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a scored snapshot")
    parser.add_argument("--id", default=datetime.now(timezone.utc).strftime("%Y-%m"),
                        help="snapshot id (default: current YYYY-MM)")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"output directory (default: {DEFAULT_OUT})")
    args = parser.parse_args()

    out_dir = Path(args.out)
    snapshot = build_snapshot(args.id)

    write_json(out_dir / "snapshots" / f"{args.id}.json", snapshot)
    write_json(out_dir / "latest.json", snapshot)
    index = rebuild_index(out_dir)

    s = snapshot["summary"]
    print(f"Published snapshot {args.id}: {s['accounts']} accounts, "
          f"tiers {s['tier_counts']}")
    print(f"  {out_dir / 'snapshots' / (args.id + '.json')}")
    print(f"  {out_dir / 'latest.json'}")
    print(f"  {out_dir / 'index.json'} ({index['count']} snapshots indexed)")


if __name__ == "__main__":
    main()
