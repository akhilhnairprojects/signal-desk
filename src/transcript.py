"""Transcript analysis, v2.

Engine: a RoBERTa-family transformer fine-tuned on financial-news sentiment
(FinBERT-class), running sentence-by-sentence through PyTorch. If the model
or PyTorch is unavailable (first install, tight memory), the module falls
back to VADER automatically and reports which engine produced the result -
the analysis never silently fails.

Adaptive learning: the pain-point taxonomy grows from user feedback. When a
reviewer flags a phrase the analyzer missed, it is stored as a learned
keyword and applied to every future transcript immediately. Sentiment
corrections accumulate as a labelled domain dataset; once enough exist,
scripts/train_domain_model.py fine-tunes the transformer on them offline.

Actionable output: next_steps() converts detected pain points, call tone,
and account context into a concrete engagement plan for the rep.
"""

import re
from collections import Counter
from datetime import date

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from src import config, store

_SPEAKER_RE = re.compile(r"^([A-Za-z .'\-]{2,30}):\s*(.+)$")

_engine = None          # ("transformer", pipeline) or ("vader", analyzer)


# ------------------------------------------------------------------ engine

def get_engine():
    """Load the best available sentiment engine once per process."""
    global _engine
    if _engine is not None:
        return _engine

    if config.TRANSCRIPT_ENGINE in ("auto", "transformer"):
        try:
            from transformers import pipeline
            clf = pipeline("text-classification",
                           model=config.SENTIMENT_MODEL,
                           top_k=None, truncation=True)
            _engine = ("transformer", clf)
            return _engine
        except Exception:
            if config.TRANSCRIPT_ENGINE == "transformer":
                raise

    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _engine = ("vader", SentimentIntensityAnalyzer())
    return _engine


def engine_name() -> str:
    kind, _ = get_engine()
    return ("Transformer (RoBERTa financial-sentiment, PyTorch)"
            if kind == "transformer" else "VADER (lexicon fallback)")


def _score_sentences(sentences: list[str]) -> list[float]:
    """Compound-style score in [-1, 1] per sentence, engine-agnostic."""
    kind, model = get_engine()
    if kind == "vader":
        return [model.polarity_scores(s)["compound"] for s in sentences]

    results = model(sentences, batch_size=16)
    scores = []
    for res in results:
        probs = {r["label"].lower(): r["score"] for r in res}
        scores.append(probs.get("positive", 0.0) - probs.get("negative", 0.0))
    return scores


# ------------------------------------------------------------- text utils

def split_sentences(text: str) -> list[str]:
    """Rough sentence split that also strips 'Speaker:' prefixes."""
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = _SPEAKER_RE.match(raw)
        lines.append(m.group(2) if m else raw)
    parts = re.split(r"(?<=[.!?])\s+", " ".join(lines))
    return [p.strip() for p in parts if len(p.strip()) > 2]


# ---------------------------------------------------------------- sentiment

def sentiment_summary(text: str) -> dict:
    sentences = split_sentences(text)
    if not sentences:
        return {"overall": 0.0, "label": "Neutral", "best": "", "worst": "",
                "engine": engine_name()}

    scores = _score_sentences(sentences)
    overall = sum(scores) / len(scores)

    if overall >= 0.2:
        label = "Positive"
    elif overall <= -0.2:
        label = "Negative"
    else:
        label = "Mixed / Neutral"

    pairs = list(zip(sentences, scores))
    best = max(pairs, key=lambda x: x[1])
    worst = min(pairs, key=lambda x: x[1])
    return {"overall": round(overall, 2), "label": label,
            "best": best[0], "worst": worst[0], "engine": engine_name()}


# --------------------------------------------------- adaptive pain points

def active_taxonomy() -> dict:
    """Config taxonomy merged with keywords learned from user feedback."""
    taxonomy = {k: list(v) for k, v in config.PAIN_POINT_TAXONOMY.items()}
    learned = store.load("learned_keywords")
    for _, row in learned.iterrows():
        cat, term = str(row["category"]), str(row["term"]).strip().lower()
        if cat in taxonomy and term and term not in taxonomy[cat]:
            taxonomy[cat].append(term)
    return taxonomy


def detect_pain_points(text: str) -> list[dict]:
    sentences = split_sentences(text)
    results = []
    for category, terms in active_taxonomy().items():
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b",
            re.IGNORECASE)
        evidence, hits = [], 0
        for s in sentences:
            found = pattern.findall(s)
            if found:
                hits += len(found)
                if len(evidence) < 3:
                    evidence.append(s)
        if hits:
            results.append({
                "category": category,
                "mentions": hits,
                "evidence": evidence,
                "positioning": config.POSITIONING_PLAYS.get(category, ""),
            })
    return sorted(results, key=lambda r: r["mentions"], reverse=True)


def learn_keyword(category: str, term: str, added_by: str = "") -> None:
    store.append("learned_keywords", {
        "category": category, "term": term.strip().lower(),
        "added_by": added_by.strip() or "Unattributed",
        "date": date.today().isoformat(),
    })


def record_feedback(account: str, predicted: str, corrected: str,
                    excerpt: str) -> None:
    store.append("transcript_feedback", {
        "date": date.today().isoformat(), "account": account,
        "predicted": predicted, "corrected": corrected,
        "excerpt": excerpt[:500],
    })


# --------------------------------------------------------------- keywords

def top_keywords(text: str, n: int = 12) -> list[tuple[str, int]]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    words = [w for w in words if w not in ENGLISH_STOP_WORDS]
    return Counter(words).most_common(n)


# -------------------------------------------------------------- next steps

_STEP_PLAYBOOK = {
    "Cost Pressure": "Build a TCO comparison against their current regional "
                     "contracts and send it before the next touchpoint.",
    "Network Performance": "Propose a network assessment of the routes they "
                           "flagged, with latency benchmarks as the deliverable.",
    "Cloud Migration": "Map their migration workloads to cloud on-ramp "
                       "options and bring a reference architecture.",
    "Security & Compliance": "Bring a security specialist to the next call "
                             "and offer a zero-trust architecture review.",
    "AI & Data Readiness": "Scope the data-movement requirements of their AI "
                           "pilots; quantify current transfer times vs target.",
    "Vendor Consolidation": "Inventory their current providers and present a "
                            "single-partner operating model with named owners.",
    "Scalability & Growth": "Map their expansion markets against coverage and "
                            "provide time-to-connect estimates per site.",
    "Support & Service": "Share the service model one-pager and offer an "
                         "intro to the named account engineering team.",
}


def next_steps(pain_points: list[dict], sentiment: dict,
               account_row=None) -> list[str]:
    """A concrete engagement plan from the call's content and tone."""
    steps = [_STEP_PLAYBOOK[p["category"]]
             for p in pain_points[:3] if p["category"] in _STEP_PLAYBOOK]

    tone = sentiment.get("label", "")
    if tone == "Positive":
        steps.append("Momentum is on your side: send the recap within 24 "
                     "hours and propose concrete dates for the next step "
                     "while goodwill is fresh.")
    elif tone == "Negative":
        steps.append("Address the strongest concern in writing before "
                     "proposing anything new, and consider bringing an "
                     "executive sponsor to rebuild confidence.")
    else:
        steps.append("The call was exploratory: convert interest into a "
                     "technical deep-dive with their architects to create "
                     "forward motion.")

    if account_row is not None:
        tier = account_row.get("tier", "")
        if tier == "Tier 1":
            steps.append("Tier 1 account - keep the cadence tight: "
                         "follow-up within one week, exec alignment within "
                         "the month.")
        elif tier == "Tier 3":
            steps.append("Tier 3 account - nurture efficiently: add them to "
                         "the relevant campaign track and revisit next "
                         "quarter unless the signals move.")
        if account_row.get("news_adj", 0):
            steps.append("Recent AI news is moving this account's score - "
                         "reference their announcements in the follow-up to "
                         "show you are tracking their strategy.")
    return steps


# ----------------------------------------------------------------- analyze

def analyze(text: str, account_row=None) -> dict:
    sentiment = sentiment_summary(text)
    pains = detect_pain_points(text)
    return {
        "sentiment": sentiment,
        "pain_points": pains,
        "keywords": top_keywords(text),
        "sentence_count": len(split_sentences(text)),
        "next_steps": next_steps(pains, sentiment, account_row),
    }
