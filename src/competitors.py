"""Competitive intelligence: what the network competitors are saying.

The account universe deliberately excludes network/connectivity
competitors - this module tracks them instead. It reuses the Google News
machinery to pull each competitor's recent coverage (not AI-only: product,
network, cloud, security, pricing, partnership news), tags every headline
with a message theme, and feeds the Competitive Intel page: the activity
matrix (competitor x theme), per-competitor feeds, and auto-generated
battlecards pairing their current messaging with our counter-positioning.
"""

import re
from urllib.parse import quote

import pandas as pd
import requests

from src import config, news, store

_THEME_RES = {
    theme: re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b",
                      re.IGNORECASE)
    for theme, terms in config.COMPETITOR_THEMES.items()
}


def categorize(title: str) -> str:
    """First matching theme in config order; 'Other' if none."""
    for theme, pattern in _THEME_RES.items():
        if pattern.search(title):
            return theme
    return "Other"


def fetch_competitor_news(name: str) -> list[dict]:
    query = quote(f'"{news.clean_name(name)}" '
                  f'when:{config.COMPETITOR_NEWS_LOOKBACK_DAYS}d')
    resp = requests.get(news.RSS_URL.format(query=query),
                        headers=news.HEADERS, timeout=10)
    resp.raise_for_status()
    articles = news.parse_rss(resp.content)
    tokens = [t.lower() for t in news._name_tokens(name)]
    kept, seen = [], set()
    for a in articles:
        t = a["title"].lower()
        if t in seen or (tokens and not any(tok in t for tok in tokens)):
            continue
        seen.add(t)
        kept.append(a)
    return kept


def collect_all(limit: int | None = None, verbose: bool = True) -> pd.DataFrame:
    """Refresh headlines for every configured competitor."""
    competitors = config.COMPETITORS[:limit] if limit else config.COMPETITORS
    rows, failures = [], 0
    for name in competitors:
        try:
            articles = fetch_competitor_news(name)
        except requests.RequestException:
            failures += 1
            continue
        for a in articles[:20]:
            rows.append({
                "account": name,
                "published": a["published"].date().isoformat(),
                "source": a["source"],
                "title": a["title"],
                "link": a["link"],
                "theme": categorize(a["title"]),
            })
        if verbose:
            print(f"  {name}: {len(articles)} headlines")
    new = pd.DataFrame(rows, columns=store.TABLES["competitor_headlines"])
    store.replace_accounts("competitor_headlines",
                           [c for c in competitors], new)
    if verbose and failures:
        print(f"  note: {failures} competitor(s) skipped (network errors)")
    return store.load("competitor_headlines")


def theme_matrix(headlines: pd.DataFrame) -> pd.DataFrame:
    """Competitor x theme headline counts - the messaging activity matrix."""
    if headlines.empty:
        return pd.DataFrame()
    themes = list(config.COMPETITOR_THEMES) + ["Other"]
    pivot = (headlines.pivot_table(index="account", columns="theme",
                                   values="title", aggfunc="count",
                                   fill_value=0)
             .reindex(columns=[t for t in themes
                               if t in headlines["theme"].unique()],
                      fill_value=0))
    return pivot


def battlecard(name: str, headlines: pd.DataFrame) -> dict:
    """Their current messaging + our counters, ready to present."""
    theirs = headlines[headlines["account"] == name]
    counts = theirs["theme"].value_counts()
    top = [t for t in counts.index if t != "Other"][:3]
    plays = []
    for theme in top:
        example = theirs[theirs["theme"] == theme].sort_values(
            "published", ascending=False).iloc[0]
        plays.append({
            "theme": theme,
            "mentions": int(counts[theme]),
            "their_message": example["title"],
            "our_counter": config.COUNTER_PLAYS.get(
                theme, "Position on global reach and delivery certainty."),
        })
    return {"competitor": name, "headline_count": len(theirs),
            "plays": plays}


def battlecard_markdown(card: dict) -> str:
    lines = [f"# Battlecard: {card['competitor']}",
             f"_Based on {card['headline_count']} headlines from the last "
             f"{config.COMPETITOR_NEWS_LOOKBACK_DAYS} days._", ""]
    for p in card["plays"]:
        lines += [f"## {p['theme']}  ({p['mentions']} mentions)",
                  f"**They are saying:** {p['their_message']}",
                  f"**Our counter:** {p['our_counter']}", ""]
    return "\n".join(lines)
