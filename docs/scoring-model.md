# The scoring model

Full working for the composite score: how version 1 was specified, what the
scored universe revealed once there was enough of it to analyse, and the
refinement that followed.

Everything below is reproducible from `results/accounts_scored.csv` and the code
in `src/`. Snippets at the end.

---

## 1. Summary

| | Version 1 | Version 2 |
|---|---|---|
| Signal inputs | raw 0–100 values | percentile ranks within the universe |
| Weights | .25 / .25 / .20 / .20 / .10 | .175 / .175 / .20 / .25 / .20 |
| Tier rule | fixed cutoffs at 80 / 60 | quantiles at the 85th / 50th percentile |
| Score range | 54.2 – 100.0 (sd 10.0) | 10.4 – 98.4 (sd 21.5) |
| Tier 1 | 47 accounts (29.4%) | 25 accounts (15.6%) |

Rank correlation between the two versions: **Spearman ρ = 0.977**. All 25
version-2 Tier 1 accounts were already Tier 1 under version 1.

---

## 2. Notation

For account $i$ and signal $j$:

- $x_{ij}$ — raw signal value, nominally 0–100
- $w_j$ — weight, $\sum_j w_j = 1$
- $S_i$ — composite base score
- $n = 160$ accounts, $p = 5$ signals

The five signals are `ai_hiring`, `ai_announce`, `cloud`, `global_reach`,
`data_centre`.

---

## 3. Version 1, and why it was specified that way

$$S_i = \sum_{j=1}^{5} w_j \, x_{ij}, \qquad
w = (0.25,\ 0.25,\ 0.20,\ 0.20,\ 0.10)$$

$$\text{tier}(S) = \begin{cases}
\text{Tier 1} & S \geq 80\\
\text{Tier 2} & 60 \leq S < 80\\
\text{Tier 3} & S < 60
\end{cases}$$

These weights were not arbitrary and they were not derived from data. They
mirrored the `MODEL WEIGHTS` block in the sales team's existing workbook.

That was the correct decision for version 1. A scoring tool is only useful if
the people it is built for recognise its answers; a model that reorders their
account list on day one gets argued with rather than used. Matching the existing
weighting meant the platform's numbers were immediately legible, and the
argument could be about the *product* rather than about whether the scores were
credible.

It also established the baseline that made everything in section 4 possible.
Version 1 scored the full universe consistently, which is what produced a
dataset to interrogate. The spreadsheet never had one.

---

## 4. What the scored universe revealed

### 4.1 Correlation structure

Pearson correlations across the 160 accounts:

|  | ai_hiring | ai_announce | cloud | global_reach | data_centre |
|---|---|---|---|---|---|
| **ai_hiring** | 1.00 | **0.94** | 0.80 | 0.23 | 0.80 |
| **ai_announce** | 0.94 | 1.00 | 0.71 | 0.37 | 0.84 |
| **cloud** | 0.80 | 0.71 | 1.00 | 0.13 | 0.50 |
| **global_reach** | 0.23 | 0.37 | 0.13 | 1.00 | 0.17 |
| **data_centre** | 0.80 | 0.84 | 0.50 | 0.17 | 1.00 |

Two things stand out. `ai_hiring` and `ai_announce` correlate at **0.94** —
high enough that they are best understood as two measurements of one underlying
behaviour (a company investing visibly in AI). And `global_reach` is close to
orthogonal to everything else ($r = 0.13$–$0.37$), making it the only signal
carrying genuinely independent information.

### 4.2 Principal components

PCA on the standardised signals:

| Component | Eigenvalue share | Cumulative |
|---|---|---|
| PC1 | **0.681** | 0.681 |
| PC2 | **0.189** | 0.870 |
| PC3 | 0.102 | 0.971 |
| PC4 | 0.021 | 0.993 |
| PC5 | 0.007 | 1.000 |

Loadings:

| Signal | PC1 | PC2 |
|---|---|---|
| ai_hiring | 0.53 | −0.11 |
| ai_announce | 0.53 | 0.06 |
| cloud | 0.44 | −0.22 |
| data_centre | 0.46 | −0.12 |
| global_reach | 0.19 | **0.96** |

87% of the variance sits in two dimensions. PC1 is a general "AI and digital
intensity" factor that four signals load onto; PC2 is almost purely global
footprint. Five inputs, two underlying factors.

### 4.3 Variance decomposition

The useful question is not what weight a signal was *assigned*, but how much it
actually moved the score. For $S = \sum_j w_j x_j$, the exact decomposition is

$$\operatorname{Var}(S) = \sum_j w_j \operatorname{Cov}(x_j, S)
\quad\Longrightarrow\quad
c_j = \frac{w_j \operatorname{Cov}(x_j, S)}{\operatorname{Var}(S)},
\qquad \sum_j c_j = 1$$

Applied to version 1 ($\operatorname{sd}(S) = 10.02$):

| Signal | $w_j$ | $\operatorname{sd}(x_j)$ | contribution $c_j$ | gap |
|---|---|---|---|---|
| ai_hiring | 25.0% | 10.16 | 22.6% | −2.4 |
| ai_announce | 25.0% | 12.09 | 28.4% | +3.4 |
| cloud | 20.0% | 8.50 | **12.2%** | **−7.8** |
| global_reach | 20.0% | 20.11 | **24.9%** | **+4.9** |
| data_centre | 10.0% | 15.54 | 11.8% | +1.8 |

The mechanism is the standard deviation column. A weight multiplies a signal, so
a signal that barely varies cannot move the score regardless of its weight.
`cloud` spans only 66–100 across the universe, so at a nominal 20% it delivered
12%. `global_reach` spans 21–100, so at the same nominal 20% it delivered 25%.

> **A note on method.** An earlier pass used the simpler heuristic
> $c_j \approx w_j \sigma_j / \sum_k w_k \sigma_k$, which put `global_reach` at
> 31.3% and `cloud` at 13.2%. That form ignores correlation and overstates an
> independent signal, because it does not account for the lower covariance
> between `global_reach` and the total. The covariance form above is exact and
> sums to 1; it is the one to quote.

### 4.4 Tier calibration

Because every signal sat high on its nominal 0–100 range, composite scores only
spanned **54.2 to 100.0** (mean 74.9, sd 10.0). Against a fixed cutoff at 80
that produced:

- Tier 1 "engage now": **47 of 160** (29.4%)
- Tier 1 or 2: 146 of 160 (91.2%)
- Tier 3: 14

The thresholds assumed scores would use the full 0–100 range. They never did.

---

## 5. The refinement

### 5.1 Percentile-rank the signals

$$r_{ij} = 100 \cdot \frac{\operatorname{rank}(x_{ij})}{n},
\qquad S_i = \sum_j w_j\, r_{ij}$$

Ties take the average rank — necessary here, because starter signal values
derive from sub-industry baselines and many accounts share an identical profile.

After the transform the five inputs have near-identical spread
($\operatorname{sd} \approx 28.8$ for all five, uniform by construction), so a
weight now multiplies a comparable quantity. Implemented in
`scoring.rank_signals()`.

### 5.2 Re-weight to the factor structure

```python
SIGNAL_WEIGHTS = {
    "ai_hiring":    0.175,   # ┐ one 0.35 AI allocation, split across the pair
    "ai_announce":  0.175,   # ┘ that correlates at r = 0.94
    "cloud":        0.20,
    "global_reach": 0.25,    # the only independent signal
    "data_centre":  0.20,
}
```

The AI pair splits a single 0.35 allocation. Since
$0.175 r_1 + 0.175 r_2 = 0.35 \cdot \frac{r_1 + r_2}{2}$, this is exactly
equivalent to averaging the pair and weighting the average at 0.35 — while
keeping both as separate columns, which matters because the measured-signal
layer updates them from different evidence (open AI job postings feed
`ai_hiring`; AI-referencing SEC filings feed `ai_announce`). Merging the columns
would have broken that.

`global_reach` takes an explicit 0.25. It was already the second-largest driver
of the score; it is now so by intent rather than as a side effect of its spread.

### 5.3 Quantile tiers

$$\text{Tier 1} = \{i : S_i \geq Q_{0.85}(S)\},\quad
\text{Tier 2} = \{i : Q_{0.50}(S) \leq S_i < Q_{0.85}(S)\},\quad
\text{Tier 3} = \text{rest}$$

Cutoffs are recomputed from the live distribution on every run, so the shortlist
stays a fixed *share* of the universe as scores drift, accounts are added, or
measured signals replace estimates. Implemented in `scoring.tier_cutoffs()`.

---

## 6. What ranking does and does not fix

Worth being precise, because it is easy to overclaim.

Ranking removes the **scale** distortion: every signal now enters on an
identical uniform distribution, so a weight is a genuine statement about how
much that signal is being asked to matter.

It does **not** equalise variance contribution, and it cannot. Re-running the
decomposition on version 2:

| Signal | $w_j$ | contribution $c_j$ | gap |
|---|---|---|---|
| ai_hiring | 17.5% | 21.6% | +4.1 |
| ai_announce | 17.5% | 22.8% | +5.3 |
| cloud | 20.0% | 20.2% | +0.2 |
| global_reach | 25.0% | **13.7%** | **−11.3** |
| data_centre | 20.0% | 21.7% | +1.7 |

`global_reach` still contributes less than its weight — now because it is
*uncorrelated* with the rest. Contribution depends on $\operatorname{Cov}(x_j,
S)$, and an independent signal covaries less with a total that is dominated by a
mutually-reinforcing block. Four correlated signals amplify each other; a lone
one does not.

This is inherent to variance decomposition of correlated inputs, not a defect.
It is also why `global_reach` earns its 0.25: in aggregate it moves the score
less, but it is the only signal capable of separating accounts that the
correlated block scores identically. Variance contribution measures influence on
the spread of scores, not usefulness for discrimination — and for a
prioritisation tool the second is what matters.

---

## 7. Validation

**Rank stability.** Spearman correlation between version 1 and version 2
adjusted scores: **ρ = 0.977** (Pearson 0.962) across all 160 accounts.

**Tier overlap.** Of the 25 accounts in version-2 Tier 1, **25 were already in
version-1 Tier 1**. Zero promotions into the top tier.

That combination is the case for the change. It does not overturn the
commercial judgement encoded in the original weights — it agrees with it about
which accounts matter, and tightens where the line falls. A refinement that
reordered the top of the list would have needed a far higher burden of proof
than one that shortens it.

**Distribution.** Version 2 spans 10.4–98.4 (sd 21.5) against version 1's
54.2–100.0 (sd 10.0). The model can now express "this account is a poor fit",
which it previously could not.

---

## 8. What this model is, and is not

- **The composite is a transparent weighted model, not a trained one.** The
  weights are reasoned from the structure above, not fitted to outcomes. This is
  deliberate: users need to see the arithmetic behind a number that reprioritises
  their week.
- **There is a trained component, scoped narrowly.**
  `scripts/train_weights.py` fits a logistic regression on logged Won / Engaged /
  Lost outcomes, clips anti-predictive coefficients at zero, normalises the
  survivors, and writes `results/learned_weights.json`. It activates only at
  ≥40 outcomes with ≥10 per class, and the configured weights remain the
  fallback. The Overview page always states which set is live.
- **The unsupervised work is genuine ML**: K-Means (k chosen by silhouette),
  HDBSCAN for density and outliers, PCA and UMAP projections, and
  nearest-neighbour lookalikes on the standardised signals.
- **The score is a percentile within this universe**, not an absolute readiness
  rating. An account at 76 sits at the 76th percentile of the 160 tracked. It is
  not "76% ready", and it is not comparable to a score from a different universe.
- **Starter signal values are estimates** from sub-industry baselines. The
  measured collectors (SEC filings, open job postings) replace them with evidence
  account by account, and the UI labels which is which.
- **Ties are real.** Accounts sharing a sub-industry baseline share a signal
  profile and therefore a score. This is a data-granularity limit, not a scoring
  bug, and it resolves as measured signals land.
- **The top of the ranking concentrates in Technology.** That is an honest output:
  technology companies genuinely score highest on AI-intensity signals.

---

## 9. Reproducing the analysis

```bash
python scripts/run_pipeline.py     # rescore; prints tier counts
python -m pytest tests/ -q         # 13 tests over the transform and tiers
```

Correlation, PCA and the variance decomposition:

```python
import numpy as np, pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from src import ingest, config

df = ingest.load_accounts()
S = list(config.SIGNAL_WEIGHTS)
X = df[S]

print(X.corr().round(2))

p = PCA().fit(StandardScaler().fit_transform(X))
print(p.explained_variance_ratio_.round(3))
print(dict(zip(S, p.components_[0].round(2))))

# exact variance decomposition for any weight vector
w = np.array([0.25, 0.25, 0.20, 0.20, 0.10])      # version 1
V = np.cov(X.values, rowvar=False)
contrib = w * (V @ w) / (w @ V @ w)                # sums to 1
print(dict(zip(S, (contrib * 100).round(1))))
```

Swap `X` for `scoring.rank_signals(df)` and `w` for the current
`config.SIGNAL_WEIGHTS` to reproduce the version-2 table in section 6.
