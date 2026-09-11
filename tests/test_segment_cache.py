"""Tests for the published segmentation cache.

Segmentation is ~99% of pipeline runtime, so it is served from a published
file. The only thing standing between that and silently stale segments is the
fingerprint, which is what these tests exercise: a cache must be used when the
inputs match and ignored the moment anything it depends on changes.
"""

import pandas as pd
import pytest

from src import config, segment

SIGNALS = list(config.SIGNAL_WEIGHTS)


def frame(n: int = 12, bump: float = 0.0) -> pd.DataFrame:
    """Small synthetic universe with enough spread for HDBSCAN's min size."""
    rows = []
    for i in range(n):
        base = (i * 7) % 100 + bump
        rows.append({
            "account": f"Account {i:02d}",
            **{s: base + j * 3 for j, s in enumerate(SIGNALS)},
            "base_score": base,
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def segmented():
    """Module-scoped: add_segments() runs UMAP, which is the slow part.
    No test mutates the frame in place, so one computation serves all."""
    df = frame()
    out, meta = segment.add_segments(df)
    return out, meta


def test_fingerprint_is_stable_for_identical_input():
    assert segment.fingerprint(frame()) == segment.fingerprint(frame())


def test_fingerprint_changes_when_a_signal_changes():
    a = frame()
    b = frame()
    b.loc[0, SIGNALS[0]] = b.loc[0, SIGNALS[0]] + 1
    assert segment.fingerprint(a) != segment.fingerprint(b)


def test_fingerprint_changes_when_an_account_is_added():
    assert segment.fingerprint(frame(12)) != segment.fingerprint(frame(13))


def test_fingerprint_changes_when_weights_change(monkeypatch):
    df = frame()
    before = segment.fingerprint(df)
    shifted = dict(config.SIGNAL_WEIGHTS)
    first, second = SIGNALS[0], SIGNALS[1]
    shifted[first] += 0.05
    shifted[second] -= 0.05
    monkeypatch.setattr(config, "SIGNAL_WEIGHTS", shifted)
    assert segment.fingerprint(df) != before


def test_cache_round_trips(segmented):
    df, meta = segmented
    cache = segment.build_cache(df, meta)
    restored, restored_meta = segment.apply_cache(df, cache)

    for col in segment.CACHE_COLUMNS:
        assert restored[col].tolist() == df[col].tolist()
    assert restored_meta["k"] == meta["k"]


def test_cache_is_rejected_when_signals_change(segmented):
    df, meta = segmented
    cache = segment.build_cache(df, meta)

    moved = df.copy()
    moved.loc[0, SIGNALS[0]] = moved.loc[0, SIGNALS[0]] + 25
    assert segment.apply_cache(moved, cache) is None


def test_cache_is_rejected_when_an_account_is_added(segmented):
    df, meta = segmented
    cache = segment.build_cache(df, meta)

    extra = pd.concat([df, df.tail(1).assign(account="Newly Added")],
                      ignore_index=True)
    assert segment.apply_cache(extra, cache) is None


def test_cache_is_rejected_on_schema_or_shape_mismatch(segmented):
    df, meta = segmented
    cache = segment.build_cache(df, meta)

    assert segment.apply_cache(df, {**cache, "schema_version": 999}) is None
    assert segment.apply_cache(df, {**cache, "fingerprint": "nope"}) is None

    truncated = {**cache, "columns": {c: v[:-1]
                                      for c, v in cache["columns"].items()}}
    assert segment.apply_cache(df, truncated) is None


def test_missing_or_unreadable_cache_is_not_fatal(segmented, monkeypatch,
                                                  tmp_path):
    df, _ = segmented
    monkeypatch.setattr(config, "SEGMENTATION_CACHE_PATH",
                        tmp_path / "absent.json")
    assert segment.load_cache() is None
    assert segment.apply_cache(df, None) is None

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(config, "SEGMENTATION_CACHE_PATH", corrupt)
    assert segment.load_cache() is None


def test_segments_falls_back_to_computing_on_a_miss(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SEGMENTATION_CACHE_PATH",
                        tmp_path / "absent.json")
    _, meta = segment.segments(frame())
    assert meta["segmentation_source"] == "computed"


def test_segments_reports_published_on_a_hit(segmented, monkeypatch, tmp_path,
                                             ):
    import json
    df, meta = segmented
    path = tmp_path / "segmentation.json"
    path.write_text(json.dumps(segment.build_cache(df, meta)), encoding="utf-8")
    monkeypatch.setattr(config, "SEGMENTATION_CACHE_PATH", path)

    out, out_meta = segment.segments(df.drop(columns=segment.CACHE_COLUMNS))
    assert out_meta["segmentation_source"] == "published"
    assert out["segment"].tolist() == df["segment"].tolist()
