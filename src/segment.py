"""Unsupervised segmentation, v2.

Two complementary clusterings on the standardised demand signals:

  - K-Means (business view): every account gets a named segment; the
    cluster count is chosen by silhouette score. These names drive the
    rest of the app.
  - HDBSCAN (analytical view): density-based clustering that handles
    overlapping groups honestly and labels genuinely unusual accounts as
    outliers instead of forcing them into a segment.

Two 2-D projections for the maps:

  - PCA: linear, preserves global structure, axes are interpretable.
  - UMAP: non-linear, separates overlapping clusters more cleanly.

UMAP is optional at runtime - if the library is unavailable the app falls
back to PCA coordinates rather than failing.
"""

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from src import config

SIGNALS = list(config.SIGNAL_WEIGHTS)

# Columns add_segments() produces, and therefore what a cache must carry.
CACHE_COLUMNS = ["cluster_id", "segment", "hdbscan_label", "density_cluster",
                 "pca_x", "pca_y", "umap_x", "umap_y"]
CACHE_SCHEMA = 1


def _choose_k(X: np.ndarray) -> tuple[int, float]:
    best_k, best_sil = None, -1.0
    for k in config.KMEANS_K_RANGE:
        labels = KMeans(n_clusters=k, random_state=config.KMEANS_RANDOM_STATE,
                        n_init=10).fit_predict(X)
        sil = silhouette_score(X, labels)
        if sil > best_sil:
            best_k, best_sil = k, sil
    return best_k, best_sil


def _umap_coords(X: np.ndarray) -> np.ndarray | None:
    try:
        import warnings
        import umap
        warnings.filterwarnings("ignore", module="umap")
        reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, n_components=2,
                            random_state=config.KMEANS_RANDOM_STATE)
        return reducer.fit_transform(X)
    except Exception:
        return None


def add_segments(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach segments, density clusters, and both projections."""
    df = df.copy()
    X = StandardScaler().fit_transform(df[SIGNALS])

    # --- K-Means business segments
    k, sil = _choose_k(X)
    df["cluster_id"] = KMeans(n_clusters=k, n_init=10,
                              random_state=config.KMEANS_RANDOM_STATE
                              ).fit_predict(X)
    order = (df.groupby("cluster_id")["base_score"].mean()
               .sort_values(ascending=False).index)
    name_map = {cid: config.SEGMENT_NAMES[i] for i, cid in enumerate(order)}
    df["segment"] = df["cluster_id"].map(name_map)

    # --- HDBSCAN density view (label -1 = outlier)
    hdb = HDBSCAN(min_cluster_size=8, copy=True).fit_predict(X)
    df["hdbscan_label"] = hdb
    df["density_cluster"] = np.where(
        hdb == -1, "Outlier",
        pd.Series(hdb).map(lambda c: f"Density group {c + 1}"))

    # --- projections
    pca = PCA(n_components=2, random_state=config.KMEANS_RANDOM_STATE)
    coords = pca.fit_transform(X)
    df["pca_x"], df["pca_y"] = coords[:, 0], coords[:, 1]

    ucoords = _umap_coords(X)
    umap_available = ucoords is not None
    if not umap_available:
        ucoords = coords
    df["umap_x"], df["umap_y"] = ucoords[:, 0], ucoords[:, 1]

    meta = {
        "k": k,
        "silhouette": round(float(sil), 3),
        "explained_variance": [round(float(v), 3)
                               for v in pca.explained_variance_ratio_],
        "hdbscan_clusters": int(len(set(hdb)) - (1 if -1 in hdb else 0)),
        "hdbscan_outliers": int((hdb == -1).sum()),
        "umap_available": umap_available,
    }
    return df, meta


# ---------------------------------------------------------------------------
# Published segmentation cache
#
# add_segments() is ~99% of pipeline runtime (the K-Means sweep, HDBSCAN and
# especially UMAP), and its output depends on nothing except the signal matrix
# and the weights that order the segment names. So it is content-addressed:
# fingerprint those inputs, and reuse a published result whenever they match.
#
# The fingerprint is what keeps this honest. Add a company, change a weight, or
# let a measured signal land, and the hash changes and the app recomputes. No
# staleness is possible — only a hit or a miss.
# ---------------------------------------------------------------------------

def fingerprint(df: pd.DataFrame) -> str:
    """Hash of everything add_segments() actually depends on."""
    from src import scoring          # local: avoids an import cycle
    weights, _ = scoring.active_weights()
    payload = {
        "schema": CACHE_SCHEMA,
        "accounts": [str(a) for a in df["account"]],
        "signals": [[round(float(v), 6) for v in row]
                    for row in df[SIGNALS].to_numpy()],
        "weights": {k: round(float(v), 6) for k, v in sorted(weights.items())},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_cache(df: pd.DataFrame, meta: dict) -> dict:
    return {
        "schema_version": CACHE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": fingerprint(df),
        "accounts": [str(a) for a in df["account"]],
        "meta": {k: v for k, v in meta.items() if k != "segmentation_source"},
        "columns": {c: df[c].tolist() for c in CACHE_COLUMNS},
    }


def load_cache() -> dict | None:
    path = config.SEGMENTATION_CACHE_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def apply_cache(df: pd.DataFrame, cache) -> tuple[pd.DataFrame, dict] | None:
    """Attach cached segmentation, or None when it does not match this frame."""
    if not cache or cache.get("schema_version") != CACHE_SCHEMA:
        return None
    if cache.get("accounts") != [str(a) for a in df["account"]]:
        return None
    if cache.get("fingerprint") != fingerprint(df):
        return None
    columns = cache.get("columns") or {}
    if any(c not in columns or len(columns[c]) != len(df) for c in CACHE_COLUMNS):
        return None

    df = df.copy()
    for col in CACHE_COLUMNS:
        df[col] = columns[col]
    return df, dict(cache.get("meta") or {})


def segments(df: pd.DataFrame, use_cache: bool = True) -> tuple[pd.DataFrame, dict]:
    """Segmentation via the published cache when it matches, else computed."""
    if use_cache:
        hit = apply_cache(df, load_cache())
        if hit is not None:
            df, meta = hit
            meta["segmentation_source"] = "published"
            return df, meta

    df, meta = add_segments(df)
    meta["segmentation_source"] = "computed"
    return df, meta


def segment_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """One row per segment: size, average signals and score, top industries."""
    rows = []
    for seg, grp in df.groupby("segment"):
        top_ind = grp["industry"].value_counts().head(3).index.tolist()
        row = {
            "segment": seg,
            "accounts": len(grp),
            "avg_score": round(grp["base_score"].mean(), 1),
            "top_industries": ", ".join(top_ind),
        }
        for col in SIGNALS:
            row[f"avg_{col}"] = round(grp[col].mean(), 1)
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("avg_score", ascending=False)
    return out.reset_index(drop=True)
