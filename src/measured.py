"""Measured signals: replace illustrative estimates with evidence.

Two collectors, both free and keyless:

  - SEC EDGAR full-text search: counts a company's AI-referencing filings
    (10-K / 10-Q / 8-K) over the last 180 days. Official, audited language -
    the strongest public commitment signal available. Feeds `ai_announce`.
    EDGAR requires a User-Agent identifying you: set EDGAR_CONTACT in
    src/config.py to your real email before running.
  - ATS public job boards (Greenhouse / Lever): counts currently-open
    AI roles. Feeds `ai_hiring`. Coverage depends on which companies
    publish through those systems - add mappings to
    data/measured/hiring_sources.csv as you find them (see PLAYBOOK).

Where a measured value exists for an account+signal, it REPLACES the
curated estimate in scoring, and the account is flagged so the UI shows
provenance. Missing measurements simply leave the estimate in place -
coverage grows account by account without ever breaking the model.
"""

import json
import re
from datetime import date, timedelta

import pandas as pd
import requests

from src import config, store

_HEADERS = {"User-Agent": f"SignalDesk/1.0 ({config.EDGAR_CONTACT})"}
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_FTS_URL = "https://efts.sec.gov/LATEST/search-index"
_CIK_CACHE = config.ROOT / "data" / "measured" / "cik_map.json"

SIGNAL_LABEL = {"ai_announce": "SEC filings", "ai_hiring": "job postings"}


# ------------------------------------------------------------ EDGAR filings

def load_cik_map(force: bool = False) -> dict:
    """ticker -> zero-padded CIK, cached locally after the first fetch."""
    if _CIK_CACHE.exists() and not force:
        return json.loads(_CIK_CACHE.read_text())
    resp = requests.get(_TICKER_MAP_URL, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    mapping = {row["ticker"].upper(): str(row["cik_str"]).zfill(10)
               for row in resp.json().values()}
    _CIK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CIK_CACHE.write_text(json.dumps(mapping))
    return mapping


def count_ai_filings(cik: str) -> int | None:
    """AI-referencing filings for one company in the lookback window.
    Returns None on any error (caller skips the account)."""
    end = date.today()
    start = end - timedelta(days=config.MEASURED_LOOKBACK_DAYS)
    try:
        resp = requests.get(_FTS_URL, headers=_HEADERS, timeout=15, params={
            "q": '"artificial intelligence"',
            "dateRange": "custom",
            "startdt": start.isoformat(),
            "enddt": end.isoformat(),
            "forms": "10-K,10-Q,8-K",
            "ciks": cik,
        })
        resp.raise_for_status()
        return int(resp.json()["hits"]["total"]["value"])
    except Exception:
        return None


# --------------------------------------------------------- ATS job postings

def _ai_role(title: str) -> bool:
    t = title.lower()
    return any(re.search(r"\b" + re.escape(k) + r"\b", t)
               for k in config.AI_ROLE_KEYWORDS)


def count_ai_postings(ats: str, token: str) -> int | None:
    """Open AI roles on a company's public Greenhouse/Lever board."""
    try:
        if ats.strip().lower() == "greenhouse":
            url = (f"https://boards-api.greenhouse.io/v1/boards/"
                   f"{token.strip()}/jobs")
            jobs = requests.get(url, timeout=15).json().get("jobs", [])
            return sum(_ai_role(j.get("title", "")) for j in jobs)
        if ats.strip().lower() == "lever":
            url = f"https://api.lever.co/v0/postings/{token.strip()}?mode=json"
            jobs = requests.get(url, timeout=15).json()
            return sum(_ai_role(j.get("text", "")) for j in jobs)
    except Exception:
        return None
    return None


def load_hiring_sources() -> pd.DataFrame:
    try:
        return pd.read_csv(config.HIRING_SOURCES_PATH).dropna()
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=["account", "ats", "board_token"])


# ------------------------------------------------------- scale and persist

def scale_filings(count: int) -> int:
    return min(count * config.FILINGS_POINTS_PER_HIT, 100)


def scale_postings(count: int) -> int:
    return min(count * config.POSTINGS_POINTS_PER_ROLE, 100)


def save_measurement(account: str, signal: str, value: int,
                     source: str) -> None:
    store.replace_where(
        "measured_signals", {"account": account, "signal": signal},
        {"account": account, "signal": signal, "value": int(value),
         "source": source, "collected_at": store.now_iso()})


# --------------------------------------------------- apply to the universe

def apply_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """Replace curated signal values with measured ones where they exist,
    and record provenance in a `measured_signals` column."""
    df = df.copy()
    df["measured_signals"] = ""
    measured = store.load("measured_signals")
    if measured.empty:
        return df
    measured["value"] = pd.to_numeric(measured["value"], errors="coerce")
    measured = measured.dropna(subset=["value"])
    for _, m in measured.iterrows():
        sig = m["signal"]
        if sig not in config.SIGNAL_WEIGHTS:
            continue
        mask = df["account"] == m["account"]
        if mask.any():
            df.loc[mask, sig] = float(m["value"])
            label = SIGNAL_LABEL.get(sig, sig)
            df.loc[mask, "measured_signals"] = (
                df.loc[mask, "measured_signals"]
                .apply(lambda s: f"{s}, {label}" if s else label))
    return df
