"""Account intelligence pipeline package."""

from src import (config, enrich, ingest, measured, news,  # noqa: F401
                 scoring, segment, similarity, store)


def build_dataset(use_segment_cache: bool = True):
    """Run the full pipeline in memory and return (df, notes, metadata).

    Single entry point for the CLI pipeline and the Streamlit app.
    Order: base score -> decayed enrichment (notes + KB) -> live news
    signal -> tiers -> segmentation (K-Means + HDBSCAN, PCA + UMAP).

    Every stage except segmentation runs in well under a second, so they all
    stay live: a note saved a moment ago moves the score on the next render.
    Segmentation is the expensive one and depends only on the signal matrix,
    so it is served from the published cache whenever the fingerprint matches
    and recomputed when it does not. Pass use_segment_cache=False to force the
    computation, which is what regenerates the cache.
    """
    df = ingest.load_accounts()
    df = measured.apply_overrides(df)
    df = scoring.add_base_score(df)

    notes = enrich.load_notes()
    kb = enrich.load_kb()
    df = enrich.apply_enrichment(df, notes, kb)
    df = news.apply_news(df)

    df = scoring.add_tiers(df, score_col="adjusted_score")
    df, meta = segment.segments(df, use_cache=use_segment_cache)
    df = similarity.build_lookalikes(df)
    meta["storage_backend"] = store.backend()
    meta["weights_source"] = scoring.active_weights()[1]
    return df, notes, meta
