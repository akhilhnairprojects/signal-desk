"""Live news signal: the Collector agent.

Pulls recent headlines per account from Google News RSS (free, no API key,
ToS-safe), keeps the ones relevant to AI infrastructure, and turns them into
a 0-100 "news momentum" score with a small, capped, non-negative adjustment
to the composite account score.

Design choices, made deliberately:
  - News can only *add* urgency. Absence of coverage is neutral, because
    smaller enterprises get less press regardless of what they are doing.
  - The adjustment is capped (config.MAX_NEWS_ADJUSTMENT) so a press-release
    blitz cannot overwhelm the underlying signal model.
  - Collection is a batch job (local run or scheduled GitHub Action), not a
    runtime fetch, so the app stays fast and never hits rate limits.
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import pandas as pd
import requests

from src import config, store

RSS_URL = ("https://news.google.com/rss/search?"
           "q={query}&hl=en-US&gl=US&ceid=US:en")
HEADERS = {"User-Agent": "Mozilla/5.0 (account-intelligence collector)"}

SIGNAL_COLUMNS = ["account", "news_score", "article_count",
                  "news_adj", "last_refreshed"]
HEADLINE_COLUMNS = ["account", "published", "source", "title", "link"]

_NAME_STOPWORDS = {"the", "inc", "corp", "group", "company", "and", "co"}


def clean_name(account: str) -> str:
    """'Alphabet (Google)' -> 'Alphabet'."""
    return account.split("(")[0].strip().rstrip(".,")


def _name_tokens(account: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9&']+", clean_name(account))
    return [t for t in tokens
            if len(t) >= 2 and t.lower() not in _NAME_STOPWORDS]


def _keyword_pattern() -> re.Pattern:
    parts = [r"\b" + re.escape(k) + r"\b" for k in config.NEWS_KEYWORDS]
    return re.compile("|".join(parts), re.IGNORECASE)


_KW_RE = _keyword_pattern()


def parse_rss(xml_bytes: bytes) -> list[dict]:
    """Parse a Google News RSS payload into article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return articles
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        pub = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        articles.append({
            "title": title.strip(),
            "link": (item.findtext("link") or "").strip(),
            "source": (item.findtext("source") or "").strip(),
            "published": published,
        })
    return articles


def fetch_company_news(account: str, timeout: int = 10) -> list[dict]:
    """Fetch recent AI-related headlines for one account."""
    query = quote(f'"{clean_name(account)}" AI when:{config.NEWS_LOOKBACK_DAYS}d')
    resp = requests.get(RSS_URL.format(query=query),
                        headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return parse_rss(resp.content)


def filter_relevant(account: str, articles: list[dict]) -> list[dict]:
    """Keep fresh articles that mention the company and an AI keyword."""
    tokens = [t.lower() for t in _name_tokens(account)]
    now = datetime.now(timezone.utc)
    kept, seen = [], set()
    for a in articles:
        age_days = (now - a["published"]).days
        if age_days > config.NEWS_LOOKBACK_DAYS or age_days < 0:
            continue
        title_l = a["title"].lower()
        if title_l in seen:
            continue
        if tokens and not any(t in title_l for t in tokens):
            continue
        if not _KW_RE.search(a["title"]):
            continue
        seen.add(title_l)
        a = dict(a, age_days=age_days)
        kept.append(a)
    return sorted(kept, key=lambda a: a["published"], reverse=True)


def score_articles(articles: list[dict]) -> int:
    """Recency-weighted momentum, mapped to 0-100."""
    points = 0.0
    for a in articles:
        recency = next((w for limit, w in config.NEWS_RECENCY_WEIGHTS
                        if a["age_days"] <= limit), 0.0)
        extra_kw = max(len(_KW_RE.findall(a["title"])) - 1, 0)
        points += recency * (1 + 0.5 * min(extra_kw, 2))
    return int(min(100, round(points * config.NEWS_SCALE)))


def score_to_adjustment(news_score: int) -> float:
    return round(news_score / 100 * config.MAX_NEWS_ADJUSTMENT, 1)


# ------------------------------------------------------------------ storage

def load_signals() -> pd.DataFrame:
    return store.load("news_signals")


def load_headlines() -> pd.DataFrame:
    return store.load("headlines")


def collect_all(accounts: list[str], limit: int | None = None,
                delay: float | None = None, verbose: bool = True) -> pd.DataFrame:
    """Fetch, score and persist news signals for the account list.

    Results merge into the existing files, so a --limit test run never
    wipes signals collected earlier for other accounts.
    """
    delay = config.NEWS_REQUEST_DELAY if delay is None else delay
    todo = accounts[:limit] if limit else accounts
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    signal_rows, headline_rows, failures = [], [], 0
    for i, account in enumerate(todo, 1):
        try:
            articles = filter_relevant(account, fetch_company_news(account))
        except requests.RequestException:
            failures += 1
            articles = []
        news_score = score_articles(articles)
        signal_rows.append({
            "account": account,
            "news_score": news_score,
            "article_count": len(articles),
            "news_adj": score_to_adjustment(news_score),
            "last_refreshed": now_iso,
        })
        for a in articles[:config.NEWS_MAX_HEADLINES]:
            headline_rows.append({
                "account": account,
                "published": a["published"].date().isoformat(),
                "source": a["source"],
                "title": a["title"],
                "link": a["link"],
            })
        if verbose and (i % 20 == 0 or i == len(todo)):
            print(f"  {i}/{len(todo)} accounts collected")
        time.sleep(delay)

    new_signals = pd.DataFrame(signal_rows, columns=SIGNAL_COLUMNS)
    new_heads = pd.DataFrame(headline_rows, columns=HEADLINE_COLUMNS)

    done = list(new_signals["account"])
    store.replace_accounts("news_signals", done, new_signals)
    store.replace_accounts("headlines", done, new_heads)

    if verbose and failures:
        print(f"  note: {failures} account(s) skipped due to network errors")
    return load_signals()


# ------------------------------------------------------- pipeline integration

def apply_news(df: pd.DataFrame, signals: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach news columns and fold the adjustment into the adjusted score.

    Must run after enrichment, since it recomputes adjusted_score as
    base + enrichment_adj + news_adj (clipped to 0-100).
    """
    df = df.copy()
    signals = load_signals() if signals is None else signals
    if signals.empty:
        df["news_score"], df["news_articles"], df["news_adj"] = 0, 0, 0.0
    else:
        s = signals.set_index("account")
        df["news_score"] = df["account"].map(s["news_score"]).fillna(0).astype(int)
        df["news_articles"] = df["account"].map(s["article_count"]).fillna(0).astype(int)
        df["news_adj"] = df["account"].map(s["news_adj"]).fillna(0.0)
    df["adjusted_score"] = (
        df["base_score"] + df["enrichment_adj"] + df["news_adj"]
    ).clip(0, 100)
    return df


def last_collected(signals: pd.DataFrame | None = None) -> str | None:
    signals = load_signals() if signals is None else signals
    if signals.empty or signals["last_refreshed"].isna().all():
        return None
    return str(signals["last_refreshed"].max())
