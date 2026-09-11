# The scoring model: what changed and why

The original model came out of a spreadsheet: five demand signals, five weights
in a `MODEL WEIGHTS` block, a weighted average, and fixed tier cutoffs at 80 and
60. That was a reasonable starting point and it encoded real judgement about
which signals matter.

This document records what happened when that model was measured against the
160 accounts it had scored, and what changed as a result. The short version:
**the weights were not doing what they said they were doing, and the tiers were
not prioritising anything.** The ranking, however, was broadly right — which is
why the fix sharpens the model rather than replacing it.

---

## What the original model was

```python
SIGNAL_WEIGHTS = {
    "ai_hiring":    0.25,
    "ai_announce":  0.25,
    "cloud":        0.20,
    "global_reach": 0.20,
    "data_centre":  0.10,
}
TIER_RULES = [("Tier 1", 80), ("Tier 2", 60), ("Tier 3", 0)]
```

`base_score = Σ(raw_signal × weight)`, with each raw signal on a 0–100 scale.

---

## Finding 1 — Five signals, two factors

PCA on the standardised signals:

| Component | Variance explained | Loads on |
|---|---|---|
| PC1 | **68.1%** | ai_hiring .53, ai_announce .53, data_centre .46, cloud .44 |
| PC2 | **18.9%** | global_reach **.96** (everything else ≤ .22) |
| PC3–5 | 13.0% | — |

87% of all variance lives in two dimensions. PC1 is a general "AI/digital
intensity" factor that four of the five signals load onto; PC2 is global
footprint, standing almost entirely alone.

The correlation matrix says the same thing more bluntly:

|  | ai_hiring | ai_announce | cloud | global_reach | data_centre |
|---|---|---|---|---|---|
| **ai_hiring** | 1.00 | **0.94** | 0.80 | 0.23 | 0.80 |
| **ai_announce** | 0.94 | 1.00 | 0.71 | 0.37 | 0.84 |
| **cloud** | 0.80 | 0.71 | 1.00 | 0.13 | 0.50 |
| **global_reach** | 0.23 | 0.37 | 0.13 | 1.00 | 0.17 |
| **data_centre** | 0.80 | 0.84 | 0.50 | 0.17 | 1.00 |

`ai_hiring` and `ai_announce` correlate at **r = 0.94**. They are not two
independent pieces of evidence; they are two measurements of one thing. Giving
them 0.25 each meant half the model's weight was spent counting the same
signal twice.

`global_reach` is the only signal that carries independent information
(r = 0.13–0.37 against everything else).

## Finding 2 — The stated weights were not the effective weights

A weight multiplies a signal, so a signal's real influence depends on how much
it *varies*. The five signals have very different spreads, so the nominal
weights and the actual contributions came apart:

| Signal | Nominal weight | std | Actual share of score variance |
|---|---|---|---|
| global_reach | 0.20 | 20.11 | **31.3%** |
| ai_announce | 0.25 | 12.09 | 23.5% |
| ai_hiring | 0.25 | 10.16 | 19.8% |
| cloud | 0.20 | 8.50 | **13.2%** |
| data_centre | 0.10 | 15.54 | 12.1% |

Two things are wrong here. `cloud` was set at 0.20 but drove 13% — its raw
values only span 66–100, so it barely separates anyone. `global_reach` was set
at the same 0.20 but drove 31%, purely because it happens to have twice the
spread of anything else.

The model presented itself as AI-led. It was in practice footprint-led, by
accident.

## Finding 3 — The tiers were not a prioritisation

Because every signal sat high on its 0–100 scale, composite scores only spanned
**54.2 to 100** (mean 74.9, std 10.0). Against fixed cutoffs of 80 and 60 that
produced:

- **Tier 1 "Engage now": 47 of 160 accounts (29.4%)**
- Tier 1 or Tier 2: 146 of 160 (91.2%)
- Tier 3 "Monitor": 14

A model that tells a sales team to engage 47 accounts immediately, and to at
least nurture 91% of the universe, has not told them anything. The tiering was
inherited from a 0–100 mental model that the actual score distribution never
matched.

---

## What changed

### 1. Percentile-rank the signals before weighting

```python
ranked = df[signals].rank(pct=True, method="average") * 100
base_score = Σ(ranked[signal] × weight)
```

Each signal now contributes exactly its assigned weight, because every signal
enters on the same uniform 0–100 distribution. This is the highest-value change
and it is what makes the weights below mean anything.

Ties share the average rank — necessary here, because starter signal values are
derived from sub-industry baselines and a lot of accounts share an identical
profile.

### 2. Rebalance to the two-factor structure

```python
SIGNAL_WEIGHTS = {
    "ai_hiring":    0.175,   # ┐ one 0.35 AI allocation, split
    "ai_announce":  0.175,   # ┘ because the two correlate at r = 0.94
    "cloud":        0.20,
    "global_reach": 0.25,    # the only independent signal
    "data_centre":  0.20,
}
```

The AI pair splits a single 0.35 allocation. Weighting them 0.175 each is
arithmetically identical to averaging the pair and weighting the average at
0.35 — but it keeps both as separate columns, which matters because the
measured-signal layer updates them from different evidence (open AI job
postings feed `ai_hiring`; AI-referencing SEC filings feed `ai_announce`).
Merging the columns would have broken that.

`global_reach` gets an explicit 0.25. It was already the largest single driver
of the score; now it is so deliberately rather than as a side effect of its
standard deviation.

`cloud` keeps 0.20 nominally but, post-ranking, now actually delivers 0.20
rather than 0.13.

### 3. Tiers become quantiles

```python
TIER_QUANTILES = [("Tier 1", 0.85), ("Tier 2", 0.50), ("Tier 3", 0.0)]
```

Tier 1 is the top 15%, Tier 2 the next 35%, Tier 3 the bottom half. Cutoffs are
computed from the live distribution on every run, so the callable list stays
callable as scores drift, new accounts are added, or measured signals replace
estimates.

---

## The result

| | Original | Revised |
|---|---|---|
| Score range | 54.2 – 100.0 | 10.4 – 98.4 |
| Std dev | 10.0 | 21.5 |
| Tier 1 | 47 (29.4%) | **25 (15.6%)** |
| Tier 2 | 99 | 57 |
| Tier 3 | 14 | 78 |
| Tier 1 score floor | 80 (fixed) | 76 (derived) |

**The ranking barely moved: Spearman ρ = 0.977** between old and new adjusted
scores.

And the sharpest evidence that this is a refinement rather than a
contradiction: **all 25 accounts in the new Tier 1 were already in the old
Tier 1.** Not one account was promoted into the top tier by the change. The new
model draws a tighter line around the same set the original model pointed at —
it agrees about direction and disagrees only about where to stop.

That matters for anyone who trusted the original spreadsheet: this does not
tell them they were wrong about their best accounts. It tells them the list was
twice as long as it needed to be.

---

## What this model still is not

Worth stating plainly, because the distinction gets blurred easily:

- **The composite is a transparent weighted model, not a trained one.** The
  weights are reasoned, not fitted. `scripts/train_weights.py` fits a logistic
  regression on logged Won/Engaged/Lost outcomes and takes over automatically
  once there are ≥40 outcomes with ≥10 per class — until then, these configured
  weights are what runs, and the Overview page always states which is active.
- **The score is a percentile, not a readiness rating.** An account scoring 76
  is at the 76th percentile of *this tracked universe*. It is not "76% ready",
  and the number is not comparable to a score from a different account list.
- **Starter signal values are estimates.** They come from sub-industry
  baselines. The measured collectors (SEC filings, open job postings) replace
  them with evidence account by account, and the UI labels which is which.
- **The top of the ranking is concentrated in Technology, and there are ties.**
  Both are honest outputs of the data: tech companies genuinely score highest on
  AI-intensity signals, and accounts sharing a sub-industry baseline share a
  profile. The ties are a data-granularity limitation, not a scoring bug — they
  resolve as measured signals land.

## Reproducing this analysis

```bash
python scripts/run_pipeline.py     # rescore; prints tier counts
```

The PCA, correlation and variance-contribution figures above come from
`results/accounts_scored.csv` using the five raw signal columns. The
Spearman comparison requires a copy of the pre-change `accounts_scored.csv`.
