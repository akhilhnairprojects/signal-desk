"""Persistent storage layer.

The spec requires that user inputs, edits, and newly added companies persist
across sessions on a stateless host. This module gives every feature one
interface with two interchangeable backends:

  - Supabase (free-tier hosted Postgres) when credentials are configured -
    via Streamlit secrets locally / on Streamlit Cloud, or environment
    variables in GitHub Actions.
  - Plain CSV files in data/ otherwise, so the project runs out of the box
    before any external service is set up, and degrades gracefully if the
    database is ever unreachable.

Every Supabase call is wrapped so a network hiccup falls back to the CSV
copy instead of crashing the app.
"""

import logging
import os
from datetime import datetime, timezone

import pandas as pd

from src import config

log = logging.getLogger(__name__)

# Failed database writes, surfaced by the app on the next page render. A read
# that falls back to CSV is normal operation; a write that fails means the
# database and the CSV mirror have diverged, and saying nothing would let the
# UI report success for an edit the database never received.
_write_failures: list[str] = []


def _write_failed(operation: str, table: str, exc: Exception) -> None:
    message = f"{operation} on '{table}' failed: {exc}"
    log.warning("Supabase %s", message)
    _write_failures.append(message)
    del _write_failures[:-5]


def pop_write_failures() -> list[str]:
    """Return and clear pending write failures."""
    failures = list(_write_failures)
    _write_failures.clear()
    return failures


TABLES = {
    "notes": ["date", "account", "author", "category", "impact", "note"],
    "kb_articles": ["account", "title", "content", "author",
                    "impact", "updated_at"],
    "custom_accounts": ["account", "ticker", "industry", "sub_industry",
                        "ai_hiring", "ai_announce", "cloud", "global_reach",
                        "data_centre", "added_by", "created_at", "rationale"],
    "news_signals": ["account", "news_score", "article_count",
                     "news_adj", "last_refreshed"],
    "headlines": ["account", "published", "source", "title", "link"],
    "transcript_feedback": ["date", "account", "predicted", "corrected",
                            "excerpt"],
    "learned_keywords": ["category", "term", "added_by", "date"],
    "measured_signals": ["account", "signal", "value", "source",
                         "collected_at"],
    "competitor_headlines": ["account", "published", "source", "title",
                             "link", "theme"],
    "outcomes": ["date", "account", "outcome", "amount", "note",
                 "logged_by"],
}

CSV_PATHS = {
    "notes": config.ENRICHMENT_PATH,
    "kb_articles": config.KB_PATH,
    "custom_accounts": config.CUSTOM_ACCOUNTS_PATH,
    "news_signals": config.NEWS_SIGNALS_PATH,
    "headlines": config.NEWS_HEADLINES_PATH,
    "transcript_feedback": config.FEEDBACK_PATH,
    "learned_keywords": config.LEARNED_KEYWORDS_PATH,
    "measured_signals": config.ROOT / "data" / "measured" / "measured_signals.csv",
    "competitor_headlines": config.ROOT / "data" / "competitors" / "headlines.csv",
    "outcomes": config.ROOT / "data" / "outcomes" / "outcomes.csv",
}

_client = None
_client_checked = False
_client_reason = ""


def _credentials() -> tuple[str, str] | None:
    global _client_reason
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not (url and key):
        try:  # Streamlit secrets, when running inside the app
            import streamlit as st
            if "supabase" in st.secrets:
                url = st.secrets["supabase"].get("url", "").strip()
                key = st.secrets["supabase"].get("key", "").strip()
            else:
                _client_reason = ("no [supabase] section in secrets "
                                  f"(found: {', '.join(st.secrets) or 'none'})")
        except Exception as exc:
            # No secrets file at all is the normal CLI / fresh-clone case,
            # not a misconfiguration worth shouting about.
            if type(exc).__name__ != "StreamlitSecretNotFoundError":
                _client_reason = f"could not read secrets: {type(exc).__name__}"
    if url and key:
        return url, key
    if not _client_reason and (url or key):
        _client_reason = (f"incomplete credentials (url {'set' if url else 'missing'}, "
                          f"key {'set' if key else 'missing'})")
    return None


def _get_client():
    """Create the Supabase client once; None means CSV mode."""
    global _client, _client_checked, _client_reason
    if _client_checked:
        return _client
    _client_checked = True
    creds = _credentials()
    if creds:
        try:
            from supabase import create_client
            _client = create_client(*creds)
            _client_reason = ""
        except Exception as exc:
            # Falling back to CSV here is correct, but doing it silently is
            # how a misconfigured deploy looks identical to a working one.
            _client = None
            _client_reason = f"{type(exc).__name__}: {exc}"
            log.warning("Supabase client unavailable - %s", _client_reason)
    return _client


def backend() -> str:
    return "supabase" if _get_client() else "csv"


def client_error() -> str:
    """Why the Supabase client is unavailable, or '' when it is fine."""
    _get_client()
    return _client_reason


def backend_label() -> str:
    if backend() == "supabase":
        return "Persistent database (Supabase)"
    reason = client_error()
    return ("Local CSV files"
            + (f" - Supabase unavailable: {reason}" if reason
               else " (set up Supabase for cloud persistence)"))


# ------------------------------------------------------------------ core I/O

def _csv_load(table: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(CSV_PATHS[table])
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=TABLES[table])
    for col in TABLES[table]:
        if col not in df.columns:
            df[col] = ""
    return df[TABLES[table]]


def _csv_save(table: str, df: pd.DataFrame) -> None:
    path = CSV_PATHS[table]
    path.parent.mkdir(parents=True, exist_ok=True)
    df[TABLES[table]].to_csv(path, index=False)


def mirror_to_csv() -> dict[str, int]:
    """Refresh every CSV mirror from the database. Read-only against Supabase.

    The repo's data/ files are meant to be a versioned mirror of the database
    (see the architecture diagram in the README). When they drift, anything
    built from the repo - the published snapshot, and therefore the
    segmentation cache keyed to it - stops matching what the deployed app
    computes from the database. Returns row counts per table.
    """
    counts = {}
    for table in TABLES:
        frame = load(table)
        _csv_save(table, frame)
        counts[table] = len(frame)
    return counts


def load(table: str) -> pd.DataFrame:
    client = _get_client()
    if client:
        try:
            rows = client.table(table).select("*").execute().data
            df = pd.DataFrame(rows)
            for col in TABLES[table]:
                if col not in df.columns:
                    df[col] = ""
            return df[TABLES[table]] if len(df) else pd.DataFrame(
                columns=TABLES[table])
        except Exception:
            pass  # fall through to CSV copy
    return _csv_load(table)


def append(table: str, row: dict) -> None:
    """Insert one row; always mirror to CSV so the repo copy stays current."""
    client = _get_client()
    if client:
        try:
            client.table(table).insert(row).execute()
        except Exception as exc:
            _write_failed("insert", table, exc)
    df = _csv_load(table)
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _csv_save(table, df)


def replace_where(table: str, match: dict, row: dict) -> None:
    """Upsert-by-match: delete rows matching `match`, insert `row`."""
    client = _get_client()
    if client:
        try:
            q = client.table(table).delete()
            for k, v in match.items():
                q = q.eq(k, v)
            q.execute()
            client.table(table).insert(row).execute()
        except Exception as exc:
            _write_failed("replace", table, exc)
    df = _csv_load(table)
    mask = pd.Series(True, index=df.index)
    for k, v in match.items():
        mask &= df[k].astype(str) == str(v)
    df = pd.concat([df[~mask], pd.DataFrame([row])], ignore_index=True)
    _csv_save(table, df)


def delete_where(table: str, match: dict) -> None:
    client = _get_client()
    if client:
        try:
            q = client.table(table).delete()
            for k, v in match.items():
                q = q.eq(k, v)
            q.execute()
        except Exception as exc:
            _write_failed("delete", table, exc)
    df = _csv_load(table)
    mask = pd.Series(True, index=df.index)
    for k, v in match.items():
        mask &= df[k].astype(str) == str(v)
    _csv_save(table, df[~mask])


def replace_accounts(table: str, accounts: list[str], new_rows: pd.DataFrame) -> None:
    """Bulk refresh used by the news collector: swap all rows for the given
    accounts with the new set."""
    client = _get_client()
    if client:
        try:
            for chunk_start in range(0, len(accounts), 100):
                chunk = accounts[chunk_start:chunk_start + 100]
                client.table(table).delete().in_("account", chunk).execute()
            records = new_rows[TABLES[table]].to_dict("records")
            for chunk_start in range(0, len(records), 200):
                client.table(table).insert(
                    records[chunk_start:chunk_start + 200]).execute()
        except Exception as exc:
            _write_failed("bulk refresh", table, exc)
    old = _csv_load(table)
    keep = old[~old["account"].isin(accounts)]
    _csv_save(table, pd.concat([keep, new_rows], ignore_index=True))


def replace_table(table: str, df: pd.DataFrame) -> None:
    """Overwrite an entire table (used by the inline notes editor)."""
    client = _get_client()
    if client:
        try:
            client.table(table).delete().gte("id", 0).execute()
            records = df[TABLES[table]].fillna("").to_dict("records")
            for i in range(0, len(records), 200):
                client.table(table).insert(records[i:i + 200]).execute()
        except Exception as exc:
            _write_failed("overwrite", table, exc)
    _csv_save(table, df)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
