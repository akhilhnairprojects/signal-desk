"""Central configuration for the account intelligence pipeline.

Everything tunable lives here: scoring weights, tier thresholds,
enrichment rules and the transcript-analysis taxonomy. Changing a
value here changes the whole pipeline and the app consistently.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]

RAW_DATA_PATH = ROOT / "data" / "raw" / "accounts.xlsx"
ENRICHMENT_PATH = ROOT / "data" / "enrichment" / "notes.csv"
RESULTS_DIR = ROOT / "results"

# Published segmentation, reused when its fingerprint matches the live signal
# matrix. Written by scripts/publish_snapshot.py; see src/segment.py.
SEGMENTATION_CACHE_PATH = ROOT / "docs" / "data" / "segmentation.json"

# Optional remote source. If the local file above is missing, the pipeline
# falls back to this URL (e.g. the raw link of the file in your GitHub repo:
# https://raw.githubusercontent.com/<user>/<repo>/main/data/raw/accounts.xlsx).
DATA_URL = ""

# ---------------------------------------------------------------------------
# Scoring model
# ---------------------------------------------------------------------------
# Applied to percentile-ranked signals (see scoring.rank_signals), so each
# weight multiplies a signal on the same uniform 0-100 distribution rather
# than one whose raw spread decides its influence.
#
# AI hiring and AI announcements correlate at r = 0.94 across the universe -
# they measure one underlying construct. Rather than merge the columns (which
# would break the measured-signal layer, where job postings and SEC filings
# update each one separately), they split a single 0.35 AI allocation between
# them. Weighting them 0.175 each is arithmetically identical to averaging
# the pair and weighting the average at 0.35.
#
# Global reach gets an explicit 0.25 because it is the only signal
# uncorrelated with the rest (r = 0.13-0.37); it was already the largest
# driver of variance by accident, and is now so by intent.
SIGNAL_WEIGHTS = {
    "ai_hiring": 0.175,
    "ai_announce": 0.175,
    "cloud": 0.20,
    "global_reach": 0.25,
    "data_centre": 0.20,
}

SIGNAL_LABELS = {
    "ai_hiring": "AI Hiring",
    "ai_announce": "AI Announcements",
    "cloud": "Cloud Presence",
    "global_reach": "Global Footprint",
    "data_centre": "Data Centre Expansion",
}

# Tier boundaries as quantiles of the live score distribution. Fixed cutoffs
# put 29% of accounts in Tier 1, which gives a sales team no order to work in;
# these keep "engage now" to a callable list however the scores drift.
TIER_QUANTILES = [
    ("Tier 1", 0.85),   # engage now  - top 15%
    ("Tier 2", 0.50),   # nurture     - next 35%
    ("Tier 3", 0.0),    # monitor     - bottom half
]

TIER_DESCRIPTIONS = {
    "Tier 1": "Engage now",
    "Tier 2": "Nurture",
    "Tier 3": "Monitor",
}

# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------
KMEANS_K_RANGE = range(3, 7)   # candidate cluster counts, chosen by silhouette
KMEANS_RANDOM_STATE = 42

# Names assigned to clusters after sorting them by average composite score.
SEGMENT_NAMES = [
    "AI Front-Runners",
    "Strong Adopters",
    "Steady Middle",
    "Late Starters",
    "Watch List",
    "Early Stage",
]

# ---------------------------------------------------------------------------
# Enrichment (field notes)
# ---------------------------------------------------------------------------
NOTE_CATEGORIES = [
    "Buying Signal",
    "Competitive Intel",
    "Relationship",
    "Risk",
    "Technical Context",
]

# Score adjustment per note, by impact. Total adjustment is capped so a
# handful of notes cannot overwhelm the underlying signal model.
IMPACT_POINTS = {"Positive": 2, "Neutral": 0, "Negative": -2}
MAX_ADJUSTMENT = 6

# ---------------------------------------------------------------------------
# Transcript analysis
# ---------------------------------------------------------------------------
# Keyword taxonomy used to surface pain points in call transcripts.
# Matching is case-insensitive on whole words/phrases.
PAIN_POINT_TAXONOMY = {
    "Cost Pressure": [
        "cost", "costs", "budget", "expensive", "spend", "pricing",
        "renewal", "overpaying", "tco",
    ],
    "Network Performance": [
        "latency", "downtime", "outage", "outages", "bandwidth",
        "slow", "packet loss", "jitter", "congestion",
    ],
    "Cloud Migration": [
        "migration", "migrate", "azure", "aws", "gcp", "cloud",
        "workload", "workloads", "hybrid", "multicloud", "multi-cloud",
    ],
    "Security & Compliance": [
        "security", "compliance", "breach", "audit", "gdpr",
        "ransomware", "zero trust", "firewall", "soc 2",
    ],
    "AI & Data Readiness": [
        "ai", "machine learning", "ml", "llm", "genai", "model",
        "data platform", "analytics", "gpu", "inference",
    ],
    "Vendor Consolidation": [
        "vendors", "consolidate", "consolidation", "single provider",
        "too many providers", "sprawl",
    ],
    "Scalability & Growth": [
        "scale", "scaling", "expansion", "expanding", "new market",
        "new markets", "growth", "capacity",
    ],
    "Support & Service": [
        "support", "ticket", "tickets", "sla", "response time",
        "escalation", "account team",
    ],
}

# Suggested positioning angle for each pain point category. These feed the
# "how to position" section of the transcript analyzer.
POSITIONING_PLAYS = {
    "Cost Pressure": "Lead with total cost of ownership: consolidated global "
                     "connectivity and predictable pricing versus fragmented "
                     "regional contracts.",
    "Network Performance": "Position the private global network story - "
                           "deterministic latency between regions and SLAs "
                           "the public internet cannot match.",
    "Cloud Migration": "Anchor on cloud on-ramps and interconnect: direct, "
                       "secure paths into Azure/AWS/GCP for the workloads "
                       "they are moving.",
    "Security & Compliance": "Bring managed security and zero-trust network "
                             "access into the conversation early; offer an "
                             "architecture review as the next step.",
    "AI & Data Readiness": "Frame AI as a data-movement problem: training "
                           "and inference need high-throughput, low-latency "
                           "paths between data centres and clouds.",
    "Vendor Consolidation": "Quantify the overhead of managing multiple "
                            "regional providers and present a single-partner "
                            "operating model.",
    "Scalability & Growth": "Map their expansion markets against network "
                            "coverage and show time-to-connect for new sites.",
    "Support & Service": "Differentiate on service model: named account "
                         "engineering and follow-the-sun support rather than "
                         "ticket queues.",
}

# ---------------------------------------------------------------------------
# Live news signal (Google News RSS collector)
# ---------------------------------------------------------------------------
NEWS_DIR = ROOT / "data" / "news"
NEWS_SIGNALS_PATH = NEWS_DIR / "news_signals.csv"
NEWS_HEADLINES_PATH = NEWS_DIR / "headlines.csv"

# Only articles from the last N days count toward the momentum score.
NEWS_LOOKBACK_DAYS = 30

# Keywords that mark a headline as AI-infrastructure relevant. Short tokens
# are matched on word boundaries, so "ai" will not match "maintain".
NEWS_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "genai",
    "generative", "llm", "gpu", "nvidia", "data center", "data centre",
    "cloud", "copilot", "openai", "anthropic", "azure", "aws",
]

# Momentum scoring: each relevant article earns recency-weighted points,
# scaled to 0-100, then mapped to a capped, non-negative score adjustment.
# News can raise urgency; silence stays neutral (small companies get less
# coverage - that should not penalise them).
NEWS_RECENCY_WEIGHTS = [(7, 1.0), (14, 0.6), (NEWS_LOOKBACK_DAYS, 0.3)]
NEWS_SCALE = 10               # points -> 0-100 score multiplier
MAX_NEWS_ADJUSTMENT = 5       # max points added to the composite score
NEWS_MAX_HEADLINES = 5        # headlines stored per account
NEWS_REQUEST_DELAY = 1.0      # seconds between RSS requests (be polite)

# ---------------------------------------------------------------------------
# Universe exclusions
# ---------------------------------------------------------------------------
# Accounts removed from the platform entirely. "3M" is excluded because the
# two-character name breaks news relevance filtering (nearly every headline
# containing "3M" is noise) and causes processing issues downstream.
EXCLUDED_ACCOUNTS = {"3M"}

# ---------------------------------------------------------------------------
# Persistent storage (v2)
# ---------------------------------------------------------------------------
KB_PATH = ROOT / "data" / "kb" / "articles.csv"
CUSTOM_ACCOUNTS_PATH = ROOT / "data" / "custom" / "custom_accounts.csv"
FEEDBACK_PATH = ROOT / "data" / "feedback" / "transcript_feedback.csv"
LEARNED_KEYWORDS_PATH = ROOT / "data" / "feedback" / "learned_keywords.csv"

# ---------------------------------------------------------------------------
# Time-decay weighting for enrichment (v2)
# ---------------------------------------------------------------------------
# Notes and KB articles carry full weight for DECAY_START_DAYS, then their
# influence halves every DECAY_HALF_LIFE_DAYS. Six-month-old intelligence
# should not steer today's call list as hard as last week's.
DECAY_START_DAYS = 180
DECAY_HALF_LIFE_DAYS = 90

# KB articles carry a lighter per-item impact than notes.
KB_IMPACT_POINTS = {"Positive": 1, "Neutral": 0, "Negative": -1}

# ---------------------------------------------------------------------------
# Transcript engine (v2)
# ---------------------------------------------------------------------------
# "auto"        try the transformer, fall back to VADER if unavailable
# "transformer" require the PyTorch model
# "vader"       force the lightweight lexicon engine
TRANSCRIPT_ENGINE = "auto"

# RoBERTa-family model fine-tuned on financial news sentiment (FinBERT-class),
# small enough for Streamlit Community Cloud.
SENTIMENT_MODEL = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"

# ---------------------------------------------------------------------------
# Auto-research for dynamically added companies (v2)
# ---------------------------------------------------------------------------
# New companies start from their industry's baseline signals (learned from
# the existing universe) and get news-derived adjustments per signal.
RESEARCH_LOOKBACK_DAYS = 90
RESEARCH_MAX_DELTA = 15          # max points news evidence can move a signal
RESEARCH_SIGNAL_KEYWORDS = {
    "ai_hiring": ["hiring", "hires", "jobs", "recruit", "talent",
                  "engineers", "headcount"],
    "cloud": ["cloud", "aws", "azure", "gcp", "saas", "multicloud",
              "migration"],
    "global_reach": ["global", "international", "expansion", "expands",
                     "worldwide", "overseas", "markets"],
    "data_centre": ["data center", "data centre", "datacenter", "capacity",
                    "gpu", "campus", "facility"],
}

# ---------------------------------------------------------------------------
# App identity (v2.2)
# ---------------------------------------------------------------------------
# Shown as the landing entry in the sidebar and as the browser-tab title.
# Change this one line to rename the app everywhere.
APP_NAME = "Signal Desk"
FAVICON_PATH = ROOT / "assets" / "favicon.png"

# ===========================================================================
# v2.3 — Enhancements 1-4
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Measured signals (replace estimates with evidence where available)
# ---------------------------------------------------------------------------
# SEC EDGAR requires a User-Agent identifying you (their fair-use policy).
# PUT YOUR REAL EMAIL HERE before running the filings collector.
EDGAR_CONTACT = "your.email@example.com"

MEASURED_LOOKBACK_DAYS = 180
# Scaling: measured raw counts -> 0-100 signal values.
FILINGS_POINTS_PER_HIT = 7     # AI-referencing SEC filings in 180d
POSTINGS_POINTS_PER_ROLE = 4   # open AI job postings right now
HIRING_SOURCES_PATH = ROOT / "data" / "measured" / "hiring_sources.csv"
AI_ROLE_KEYWORDS = ["ai", "artificial intelligence", "machine learning",
                    "ml engineer", "data scientist", "deep learning",
                    "llm", "genai", "generative ai"]

# ---------------------------------------------------------------------------
# 2. Competitive intelligence
# ---------------------------------------------------------------------------
# Network/connectivity competitors (excluded from the account universe by
# design; tracked here as competitors instead). Edit freely.
COMPETITORS = [
    "AT&T Business", "Verizon Business", "Lumen Technologies",
    "NTT Communications", "Orange Business", "BT Group",
    "Telefonica Tech", "Comcast Business", "Zayo", "GTT Communications",
]

COMPETITOR_THEMES = {
    "AI & Automation": ["ai", "artificial intelligence", "genai", "copilot",
                        "machine learning", "automation"],
    "Network & Connectivity": ["network", "fiber", "5g", "sd-wan", "wan",
                               "ethernet", "wavelength", "backbone",
                               "subsea", "latency"],
    "Cloud & Edge": ["cloud", "edge", "aws", "azure", "multicloud",
                     "colocation", "interconnect"],
    "Security": ["security", "zero trust", "ddos", "sase", "cyber",
                 "firewall"],
    "Partnerships & M&A": ["partnership", "acquisition", "acquire",
                           "merger", "alliance", "joint venture"],
    "Pricing & Packaging": ["pricing", "price", "bundle", "discount",
                            "subscription", "as-a-service"],
}

# Counter-positioning per theme - feeds the auto-generated battlecards and
# the competitive messaging matrix. Written for a generic global network
# services provider; swap in your own messaging.
COUNTER_PLAYS = {
    "AI & Automation": "Position AI-ready infrastructure end-to-end: "
        "predictable low-latency data movement between clouds, DCs and "
        "edge - the part AI pilots break first.",
    "Network & Connectivity": "Lead with end-to-end route ownership and "
        "measurable SLAs on the corridors their announcement does not cover.",
    "Cloud & Edge": "Neutral multi-cloud interconnect story: no "
        "hyperscaler lock-in, consistent performance across providers.",
    "Security": "Converge network + security (SASE/zero-trust) on one "
        "fabric instead of bolted-on point products.",
    "Partnerships & M&A": "Integration turbulence is a switching window: "
        "emphasise stability, named engineering teams, and migration "
        "assistance.",
    "Pricing & Packaging": "Reframe from price to cost-of-outage and "
        "growth flexibility; usage-aligned commercial models.",
}
COMPETITOR_NEWS_LOOKBACK_DAYS = 30

# ---------------------------------------------------------------------------
# 3. Outcome loop -> learned weights
# ---------------------------------------------------------------------------
OUTCOME_TYPES = ["Won", "Engaged", "No Response", "Lost"]
POSITIVE_OUTCOMES = {"Won", "Engaged"}
TRAIN_MIN_OUTCOMES = 40      # total outcomes before training is meaningful
TRAIN_MIN_PER_CLASS = 10     # need both positives and negatives
USE_LEARNED_WEIGHTS = True   # auto-activates once learned_weights.json exists

# ---------------------------------------------------------------------------
# 4. Push: digest email / Teams + tier-change alerts
# ---------------------------------------------------------------------------
# Credentials come from environment variables (GitHub Actions secrets):
#   SMTP_USER, SMTP_PASSWORD, DIGEST_TO   (email; Gmail app password works)
#   TEAMS_WEBHOOK_URL                     (Teams incoming webhook)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
