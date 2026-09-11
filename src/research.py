"""Dynamic account addition: the auto-research workflow.

When a user adds a new company, the platform researches it automatically and
scores it with the same five-signal structure as the baseline universe:

  1. Start from the industry baseline - the average signal profile of
     existing accounts in the chosen industry (the same construction the
     original workbook used for its starter values).
  2. Pull the company's recent news (Google News RSS, 90-day window) and
     translate keyword evidence into per-signal adjustments, capped at
     ±RESEARCH_MAX_DELTA points so news can refine but not invent a profile.
  3. Persist the account, its rationale, and its headlines, so it appears
     everywhere - explorer, segments, news monitor - like any other account.

Every produced number is traceable: the rationale strings record exactly
which baseline and which evidence moved each signal.
"""

import re
from urllib.parse import quote

import pandas as pd
import requests

from src import config, news, store

SIGNALS = list(config.SIGNAL_WEIGHTS)


def _research_fetch(name: str) -> list[dict]:
    """Wider-window news fetch used only at research time."""
    query = quote(f'"{news.clean_name(name)}" '
                  f'when:{config.RESEARCH_LOOKBACK_DAYS}d')
    resp = requests.get(news.RSS_URL.format(query=query),
                        headers=news.HEADERS, timeout=10)
    resp.raise_for_status()
    articles = news.parse_rss(resp.content)
    # Reuse the company-token filter, but keep the wider date window.
    tokens = [t.lower() for t in news._name_tokens(name)]
    kept, seen = [], set()
    for a in articles:
        t = a["title"].lower()
        if t in seen or (tokens and not any(tok in t for tok in tokens)):
            continue
        seen.add(t)
        kept.append(a)
    return kept


def industry_baseline(baseline_df: pd.DataFrame,
                      industry: str | None) -> tuple[dict, str]:
    """Average signal profile for the industry (or the whole universe)."""
    pool = baseline_df
    label = "universe average"
    if industry and industry in set(baseline_df["industry"]):
        pool = baseline_df[baseline_df["industry"] == industry]
        label = f"{industry} industry baseline ({len(pool)} accounts)"
    return {s: round(float(pool[s].mean()), 1) for s in SIGNALS}, label


def _keyword_hits(titles: list[str], terms: list[str]) -> int:
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE)
    return sum(len(pattern.findall(t)) for t in titles)


def research_company(name: str, baseline_df: pd.DataFrame,
                     industry: str | None = None,
                     sub_industry: str | None = None) -> dict:
    """Run the research workflow. Returns the full profile without saving."""
    baseline, baseline_label = industry_baseline(baseline_df, industry)
    signals = dict(baseline)
    rationale = [f"Baseline: {baseline_label}."]

    try:
        articles = _research_fetch(name)
        fetch_error = None
    except requests.RequestException as e:
        articles, fetch_error = [], str(e)

    titles = [a["title"] for a in articles]

    # AI announcement momentum from the standard news scorer (30d weighting
    # inside the wider pull still favours the freshest coverage).
    ai_hits = [a for a in articles if news._KW_RE.search(a["title"])]
    ai_delta = min(len(ai_hits) * 3, config.RESEARCH_MAX_DELTA)
    if ai_delta:
        signals["ai_announce"] = signals["ai_announce"] + ai_delta
        rationale.append(f"AI Announcements +{ai_delta}: "
                         f"{len(ai_hits)} AI-related headlines in "
                         f"{config.RESEARCH_LOOKBACK_DAYS} days.")

    for signal, terms in config.RESEARCH_SIGNAL_KEYWORDS.items():
        hits = _keyword_hits(titles, terms)
        delta = min(hits * 3, config.RESEARCH_MAX_DELTA)
        if delta:
            signals[signal] = signals[signal] + delta
            rationale.append(
                f"{config.SIGNAL_LABELS[signal]} +{delta}: "
                f"{hits} keyword mentions in recent coverage.")

    if not articles:
        rationale.append(
            "No recent coverage found - profile rests on the industry "
            "baseline." + (f" (fetch issue: network)" if fetch_error else ""))

    signals = {s: int(max(0, min(100, round(v)))) for s, v in signals.items()}
    return {
        "account": name.strip(),
        "ticker": "",
        "industry": industry or "Unclassified",
        "sub_industry": sub_industry or "",
        **signals,
        "rationale": " ".join(rationale),
        "articles": articles,
    }


def add_company(profile: dict, added_by: str = "") -> None:
    """Persist a researched profile plus its headline evidence."""
    row = {k: profile[k] for k in store.TABLES["custom_accounts"]
           if k in profile}
    row["added_by"] = added_by.strip() or "Unattributed"
    row["created_at"] = store.now_iso()
    row["rationale"] = profile.get("rationale", "")
    store.replace_where("custom_accounts",
                        {"account": profile["account"]}, row)

    articles = news.filter_relevant(profile["account"],
                                    profile.get("articles", []))
    if articles:
        heads = pd.DataFrame([{
            "account": profile["account"],
            "published": a["published"].date().isoformat(),
            "source": a["source"],
            "title": a["title"],
            "link": a["link"],
        } for a in articles[:config.NEWS_MAX_HEADLINES]])
        store.replace_accounts("headlines", [profile["account"]], heads)


def remove_company(name: str) -> None:
    store.delete_where("custom_accounts", {"account": name})
