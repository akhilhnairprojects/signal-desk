# Signal Desk

An account intelligence platform for enterprise network services. It scores 160
Americas enterprises on AI-driven connectivity demand, keeps itself current
through nightly news collection and weekly evidence gathering, tracks
competitors, learns its scoring weights from logged engagement outcomes, and
persists everything users add.

Built during a summer internship at a global B2B network services provider,
then rebuilt as a portfolio project: employer branding removed, seeded field
notes replaced with synthetic samples, and the scoring model re-derived from
the data rather than inherited from the source spreadsheet.

**Live app:** https://signal-desk-project.streamlit.app/

**Published results:** https://akhilhnairprojects.github.io/signal-desk/ —
versioned, self-describing JSON snapshots of the scored universe. No account, no
key, no running server. Each snapshot carries the model configuration that
produced it and the commit it came from, so the numbers stay interpretable and
reproducible after the app itself has moved on.

---

## What it does

| Capability | Where |
|---|---|
| Percentile-ranked 0–100 scoring with quantile tiers, a per-account score waterfall, and click-to-cross-filter tier charts | Overview, Account Explorer |
| Side-by-side comparison, nearest-neighbour lookalikes, and segment highlighting that persists across pages | Account Explorer, Segments |
| K-Means segments plus an HDBSCAN density/outlier view, on PCA and UMAP projections | Segments |
| Nightly AI-news collection per account, with an on-demand live headline check | News Monitor |
| Measured signals — AI-referencing SEC filings and open AI job postings replace estimates with evidence, with visible provenance | weekly collector → Explorer |
| Competitor headlines theme-tagged into an activity matrix, with generated battlecards | Competitive Intel |
| Inline-editable field notes and KB articles with 6-month time decay | Knowledge Base |
| Dynamic company addition with automated, evidence-traced research | Add a Company |
| Transcript analysis — sentence-level sentiment, pain points, next-step plans, and a correction feedback loop | Transcript Analyzer |
| Outcome learning loop — logged Won/Lost outcomes fit the signal weights by logistic regression, with configured weights as fallback | Explorer → `scripts/train_weights.py` |

## The scoring model

`adjusted_score = base + enrichment (±6, 6-month decay) + news momentum (0 to +5)`

The base score is a weighted composite of five demand signals, **percentile-ranked
across the universe before weighting**. Tiers are quantiles: Tier 1 is the top 15%.

Version 1 deliberately mirrored the weighting the sales team already used
(.25/.25/.20/.20/.10 on raw values, fixed tier cutoffs at 80/60). That was the
right call for adoption — a scoring tool only gets used if the people it is for
recognise its answers — and it produced the first consistently scored universe,
which is what made the following analysis possible:

- PCA puts **87% of the variance in two factors** (68% + 19%): a general
  AI-intensity factor that four signals load onto, and global footprint almost
  alone on the second.
- AI Hiring and AI Announcements correlate at **r = 0.94** — effectively two
  measurements of one behaviour.
- An exact variance decomposition showed spread, not weight, was driving
  influence: Cloud Presence sat at a nominal 20% and contributed **12.2%**,
  while Global Footprint was also 20% and contributed **24.9%**.
- Fixed cutoffs put **29% of accounts in "engage now"** (47 of 160), because
  scores only ever spanned 54–100.

The refinement ranks each signal before weighting, gives the correlated AI pair
one shared allocation, and sets tier boundaries by quantile. Tier 1 tightened to
25 accounts, **all 25 already Tier 1 under version 1**, with the two rankings
agreeing at **Spearman 0.977** — sharper, without contradicting the commercial
judgement already built in.

Full working — correlation matrix, PCA loadings, the decomposition derivation,
what ranking does and does not fix, and runnable snippets:
**[docs/scoring-model.md](docs/scoring-model.md)**.

### What it is and is not

The composite is a **transparent weighted model, not a trained one** — the
weights are reasoned, not fitted. The learning is real but scoped:
`scripts/train_weights.py` fits a logistic regression on logged outcomes and
takes over automatically once there are ≥40 with ≥10 per class. K-Means,
HDBSCAN, PCA, UMAP and nearest-neighbour lookalikes are genuine unsupervised
ML over the signal space. The score itself is a **percentile within this
universe**, not an absolute readiness rating.

## Architecture

```
                    ┌──────────────────────────────┐
                    │  GitHub repo                  │
                    │  code · workbook · CSV mirrors│
                    └────┬──────────────▲───────────┘
       deploys on push   │              │  nightly + weekly commits
                         ▼              │
  ┌──────────────┐   ┌──────────────────────┐   ┌─────────────────────┐
  │  Supabase    │◄─►│  Streamlit Cloud     │   │  GitHub Actions     │
  │  (Postgres)  │   │  8 pages             │   │  nightly: news +    │
  │  notes · KB  │◄──┤  all edits write     ├──►│    competitors      │
  │  outcomes    │   │  through store.py    │   │  weekly: measured   │
  │  companies   │   └──────────────────────┘   │    signals + digest │
  └──────────────┘                              └──────────┬──────────┘
                     SEC EDGAR · Google News ·             │
                     Greenhouse / Lever boards             ▼
                                                    email / Teams
```

`src/store.py` runs against Supabase when credentials exist and falls back to
the committed CSVs when they do not, so the app runs with **zero configuration**.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt
python scripts/run_pipeline.py
streamlit run streamlit_app.py
```

Optional, to populate live data:

```bash
python scripts/collect_news.py --limit 15
python scripts/collect_competitor_news.py --limit 3
python scripts/run_pipeline.py
```

Tests:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

`torch` and `transformers` are **not** dependencies — transcript sentiment falls
back to VADER, and the app names the active engine. See
[docs/deployment.md](docs/deployment.md) for why, and for the full free-hosting
guide.

## Layout

```
streamlit_app.py     entry point, navigation, branding
views/               the 8 app pages (not pages/ - see streamlit_app.py)
src/                 pipeline: ingest, scoring, segment, news, transcript, store
scripts/             CLI: run_pipeline, collectors, train_weights, publish_snapshot
tests/               scoring and tier-assignment tests
docs/                scoring-model.md, deployment.md, and the published site
docs/data/           versioned result snapshots (index.json, latest.json)
setup/               Supabase schema and RLS policies
data/raw/            the source workbook (required)
```

`src/` deliberately has no Streamlit imports except in `app_helpers.py`, so the
pipeline stays usable from CLI, CI, and any future front end.

## Data provenance

The 160 accounts are public companies. Starter signal values are illustrative
estimates derived from sub-industry baselines; the measured collectors replace
them with evidence account by account and the UI labels which is which. Field
notes shipped in `data/enrichment/notes.csv` are **synthetic samples**, not real
account intelligence. Network competitors are excluded from the universe by
design and tracked separately.

## Roadmap

- Migrate the front end to Next.js with an Expo iOS/Android client against the
  same Supabase backend (`notes/roadmap-native-app.md`)
- CRM export of tier lists and next-step plans
- EMEA / APAC account universes via config-driven regional workbooks
