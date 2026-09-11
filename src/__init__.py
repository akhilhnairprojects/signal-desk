"""Account intelligence pipeline package."""

from src import (config, enrich, ingest, measured, news,  # noqa: F401
                 scoring, segment, similarity, store)


def build_dataset():
    """Run the full pipeline in memory and return (df, notes, metadata).

    Single entry point for the CLI pipeline and the Streamlit app.
    Order: base score -> decayed enrichment (notes + KB) -> live news
    signal -> tiers -> segmentation (K-Means + HDBSCAN, PCA + UMAP).
    """
    df = ingest.load_accounts()
    df = measured.apply_overrides(df)
    df = scoring.add_base_score(df)

    notes = enrich.load_notes()
    kb = enrich.load_kb()
    df = enrich.apply_enrichment(df, notes, kb)
    df = news.apply_news(df)

    df = scoring.add_tiers(df, score_col="adjusted_score")
    df, meta = segment.add_segments(df)
    df = similarity.build_lookalikes(df)
    meta["storage_backend"] = store.backend()
    meta["weights_source"] = scoring.active_weights()[1]
    return df, notes, meta
