"""Composite scoring and tier assignment.

Two deliberate choices here, both of which changed after measuring the
model against the scored universe (see docs/scoring-model.md):

1. Signals are percentile-ranked within the universe before they are
   weighted. Raw spreads differ by more than 2x - global reach has a
   standard deviation of 20.1 against cloud presence's 8.5 - and a weight
   cannot move a signal that barely varies. On raw values, cloud sat at a
   nominal 0.20 and contributed 12.2% of score variance while global reach
   was also 0.20 and contributed 24.9%. Ranking puts every signal on the
   same uniform distribution, so a weight multiplies a comparable quantity.
   It does not equalise variance contribution - correlation structure still
   drives that. See docs/scoring-model.md section 6.

2. Tiers are quantiles, not fixed cutoffs. Absolute 80/60 thresholds put
   29% of the universe in "engage now", which is not a prioritisation.

Because the score is now a percentile, it reads as "where this account
sits against the others we track", not as an absolute readiness rating.
"""

import json

import pandas as pd

from src import config


def active_weights() -> tuple[dict, str]:
    """Learned weights when trained + enabled, else the configured ones.
    Returns (weights, provenance_string)."""
    path = config.RESULTS_DIR / "learned_weights.json"
    if config.USE_LEARNED_WEIGHTS and path.exists():
        try:
            data = json.loads(path.read_text())
            weights = data.get("weights", {})
            if (set(weights) == set(config.SIGNAL_WEIGHTS)
                    and abs(sum(weights.values()) - 1) < 0.02):
                return weights, (f"learned from {data.get('n_outcomes', '?')} "
                                 "logged outcomes")
        except Exception:
            pass
    return dict(config.SIGNAL_WEIGHTS), "configured"


def rank_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Percentile-rank each signal across the universe, 0-100.

    Ties share the average rank, so identical signal profiles - common,
    because starter values come from sub-industry baselines - score the same
    rather than being ordered arbitrarily.
    """
    signals = list(config.SIGNAL_WEIGHTS)
    return df[signals].rank(pct=True, method="average") * 100


def add_base_score(df: pd.DataFrame) -> pd.DataFrame:
    """Weighted composite over the percentile-ranked signals."""
    df = df.copy()
    weights, _ = active_weights()
    ranked = rank_signals(df)
    df["base_score"] = sum(ranked[col] * w
                           for col, w in weights.items()).round(1)
    return df


def tier_cutoffs(scores: pd.Series) -> list[tuple[str, float]]:
    """Score floor for each tier, derived from the live distribution."""
    return [(tier, float(scores.quantile(q)))
            for tier, q in config.TIER_QUANTILES]


def assign_tier(score: float, cutoffs: list[tuple[str, float]]) -> str:
    for tier, floor in cutoffs:
        if score >= floor:
            return tier
    return cutoffs[-1][0]


def add_tiers(df: pd.DataFrame,
              score_col: str = "adjusted_score") -> pd.DataFrame:
    df = df.copy()
    cutoffs = tier_cutoffs(df[score_col])
    df["tier"] = df[score_col].apply(assign_tier, cutoffs=cutoffs)
    df["tier_action"] = df["tier"].map(config.TIER_DESCRIPTIONS)
    return df
