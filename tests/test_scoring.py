"""Tests for the scoring transform and tier assignment.

These cover the parts of the model that are easy to break silently: the
percentile transform, the quantile tier boundaries, and the fallback that
keeps configured weights in play when learned weights are absent or corrupt.
"""

import pandas as pd
import pytest

from src import config, scoring

SIGNALS = list(config.SIGNAL_WEIGHTS)


def frame(rows: list[list[float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=SIGNALS)


def test_weights_sum_to_one():
    assert sum(config.SIGNAL_WEIGHTS.values()) == pytest.approx(1.0)


def test_ai_pair_splits_one_allocation_evenly():
    """The pair correlates at r=0.94, so they share a single allocation
    rather than counting as two independent signals."""
    assert (config.SIGNAL_WEIGHTS["ai_hiring"]
            == config.SIGNAL_WEIGHTS["ai_announce"])


def test_rank_signals_is_scale_invariant():
    """The whole point of ranking: a signal's spread stops deciding its
    influence, so rescaling one column must not move the ranks."""
    base = frame([[10, 10, 10, 10, 10],
                  [20, 20, 20, 20, 20],
                  [30, 30, 30, 30, 30]])
    stretched = base.copy()
    stretched["global_reach"] = [1, 5000, 90000]

    pd.testing.assert_frame_equal(scoring.rank_signals(base),
                                  scoring.rank_signals(stretched))


def test_rank_signals_gives_ties_the_same_rank():
    ranked = scoring.rank_signals(frame([[5, 5, 5, 5, 5],
                                         [5, 5, 5, 5, 5],
                                         [9, 9, 9, 9, 9]]))
    assert ranked["cloud"].iloc[0] == ranked["cloud"].iloc[1]
    assert ranked["cloud"].iloc[2] > ranked["cloud"].iloc[0]


def test_base_score_orders_accounts_by_signal_strength():
    df = scoring.add_base_score(frame([[10, 10, 10, 10, 10],
                                       [50, 50, 50, 50, 50],
                                       [90, 90, 90, 90, 90]]))
    assert list(df["base_score"]) == sorted(df["base_score"])


def test_tier_cutoffs_follow_the_distribution():
    scores = pd.Series(range(100))
    cutoffs = dict(scoring.tier_cutoffs(scores))
    assert cutoffs["Tier 1"] == pytest.approx(scores.quantile(0.85))
    assert cutoffs["Tier 3"] == pytest.approx(scores.min())


def test_assign_tier_is_inclusive_at_the_floor():
    cutoffs = [("Tier 1", 80.0), ("Tier 2", 50.0), ("Tier 3", 0.0)]
    assert scoring.assign_tier(80.0, cutoffs) == "Tier 1"
    assert scoring.assign_tier(79.9, cutoffs) == "Tier 2"
    assert scoring.assign_tier(50.0, cutoffs) == "Tier 2"
    assert scoring.assign_tier(49.9, cutoffs) == "Tier 3"


def test_add_tiers_keeps_tier_one_near_the_top_fifteen_percent():
    """The calibration that mattered: fixed cutoffs put 29% in Tier 1."""
    df = pd.DataFrame({"adjusted_score": range(200)})
    tiered = scoring.add_tiers(df, score_col="adjusted_score")
    share = (tiered["tier"] == "Tier 1").mean()
    assert 0.13 <= share <= 0.17


def test_add_tiers_labels_every_row():
    df = pd.DataFrame({"adjusted_score": [1.0, 50.0, 99.0]})
    tiered = scoring.add_tiers(df, score_col="adjusted_score")
    assert tiered["tier"].notna().all()
    assert tiered["tier_action"].notna().all()


def test_active_weights_falls_back_to_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    weights, provenance = scoring.active_weights()
    assert weights == config.SIGNAL_WEIGHTS
    assert provenance == "configured"


def test_active_weights_rejects_learned_weights_that_do_not_sum_to_one(
        tmp_path, monkeypatch):
    """A corrupt or partially-written file must not silently reweight the
    whole portfolio."""
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(config, "USE_LEARNED_WEIGHTS", True)
    (tmp_path / "learned_weights.json").write_text(
        '{"weights": {"ai_hiring": 0.9, "ai_announce": 0.9, "cloud": 0.9,'
        ' "global_reach": 0.9, "data_centre": 0.9}}')

    weights, provenance = scoring.active_weights()
    assert provenance == "configured"
    assert weights == config.SIGNAL_WEIGHTS


def test_active_weights_rejects_learned_weights_with_missing_signals(
        tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(config, "USE_LEARNED_WEIGHTS", True)
    (tmp_path / "learned_weights.json").write_text(
        '{"weights": {"ai_hiring": 1.0}}')

    _, provenance = scoring.active_weights()
    assert provenance == "configured"


def test_active_weights_accepts_valid_learned_weights(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(config, "USE_LEARNED_WEIGHTS", True)
    (tmp_path / "learned_weights.json").write_text(
        '{"weights": {"ai_hiring": 0.2, "ai_announce": 0.2, "cloud": 0.2,'
        ' "global_reach": 0.2, "data_centre": 0.2}, "n_outcomes": 55}')

    weights, provenance = scoring.active_weights()
    assert weights["ai_hiring"] == 0.2
    assert "55" in provenance
