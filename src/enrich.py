"""Continuous enrichment: field notes and the knowledge base, with time decay.

Two kinds of enrichment feed the score:
  - Field notes (quick observations): ±2 points each by impact.
  - Knowledge base articles (longer-lived context, editable in-app):
    ±1 point each by impact.

Both decay: full weight for the first six months, then influence halves
every 90 days, so old intelligence fades from the ranking instead of
steering it forever. The combined adjustment is capped at ±6 per account;
if the raw sum exceeds the cap it is scaled down proportionally, keeping
the note-vs-KB split honest for the score breakdown chart.
"""

from datetime import date, datetime, timezone

import pandas as pd

from src import config, store

NOTE_COLUMNS = store.TABLES["notes"]
KB_COLUMNS = store.TABLES["kb_articles"]


# ------------------------------------------------------------------ decay

def decay_weight(age_days: float) -> float:
    """1.0 while fresh, halving every DECAY_HALF_LIFE_DAYS after the start."""
    if pd.isna(age_days) or age_days <= config.DECAY_START_DAYS:
        return 1.0
    extra = age_days - config.DECAY_START_DAYS
    return 0.5 ** (extra / config.DECAY_HALF_LIFE_DAYS)


def _age_days(series: pd.Series) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    now = pd.Timestamp.now(tz="UTC")
    return (now - dates).dt.days.astype("float")


# ------------------------------------------------------------------ notes

def load_notes() -> pd.DataFrame:
    return store.load("notes")


def append_note(account: str, author: str, category: str, impact: str,
                note: str) -> None:
    store.append("notes", {
        "date": date.today().isoformat(),
        "account": account,
        "author": author.strip() or "Unattributed",
        "category": category,
        "impact": impact,
        "note": note.strip(),
    })


# ------------------------------------------------------------------ KB

def load_kb() -> pd.DataFrame:
    return store.load("kb_articles")


def save_kb_article(account: str, title: str, content: str, author: str,
                    impact: str = "Neutral") -> None:
    """Create or update an article (matched on account + title). Editing
    stamps updated_at, which resets the decay clock - reviewed knowledge
    counts as fresh knowledge."""
    store.replace_where(
        "kb_articles",
        {"account": account, "title": title.strip()},
        {"account": account, "title": title.strip(),
         "content": content.strip(),
         "author": author.strip() or "Unattributed",
         "impact": impact,
         "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    )


def delete_kb_article(account: str, title: str) -> None:
    store.delete_where("kb_articles", {"account": account, "title": title})


# ------------------------------------------------- adjustments and scoring

def _decayed_points(df: pd.DataFrame, date_col: str,
                    points_map: dict) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    pts = df["impact"].map(points_map).fillna(0).astype(float)
    weights = _age_days(df[date_col]).map(decay_weight)
    return (pts * weights).groupby(df["account"]).sum()


def apply_enrichment(df: pd.DataFrame, notes: pd.DataFrame,
                     kb: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach note_adj, kb_adj and the capped combined enrichment_adj."""
    df = df.copy()
    kb = load_kb() if kb is None else kb

    note_pts = _decayed_points(notes, "date", config.IMPACT_POINTS)
    kb_pts = _decayed_points(kb, "updated_at", config.KB_IMPACT_POINTS)

    df["note_count"] = df["account"].map(
        notes.groupby("account").size() if not notes.empty
        else pd.Series(dtype=int)).fillna(0).astype(int)
    df["kb_count"] = df["account"].map(
        kb.groupby("account").size() if not kb.empty
        else pd.Series(dtype=int)).fillna(0).astype(int)

    df["note_adj"] = df["account"].map(note_pts).fillna(0.0)
    df["kb_adj"] = df["account"].map(kb_pts).fillna(0.0)

    combined = df["note_adj"] + df["kb_adj"]
    over = combined.abs() > config.MAX_ADJUSTMENT
    scale = pd.Series(1.0, index=df.index)
    scale[over] = config.MAX_ADJUSTMENT / combined[over].abs()
    df["note_adj"] = (df["note_adj"] * scale).round(1)
    df["kb_adj"] = (df["kb_adj"] * scale).round(1)
    df["enrichment_adj"] = (df["note_adj"] + df["kb_adj"]).round(1)

    df["adjusted_score"] = (df["base_score"] + df["enrichment_adj"]).clip(0, 100)
    return df


def current_weight(date_value) -> float:
    """Today's decay weight for a single note/article date (for the UI)."""
    age = _age_days(pd.Series([date_value])).iloc[0]
    return round(decay_weight(age), 2)
