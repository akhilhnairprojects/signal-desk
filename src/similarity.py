"""Lookalike accounts via nearest neighbours on the standardised signals.

Used for the "accounts similar to X" feature: if a positioning story worked
for one account, its nearest neighbours are the natural next calls.

Note on ties: several accounts can share an identical signal profile
(distance 0.00) because the starter values are built from sub-industry
baselines. The query account is therefore excluded by identity, never by
position - dropping "the first result" is not safe when distances tie.
"""

import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from src import config

SIGNALS = list(config.SIGNAL_WEIGHTS)


def build_lookalikes(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Attach a 'lookalikes' column with the n most similar accounts."""
    df = df.copy()
    X = StandardScaler().fit_transform(df[SIGNALS])

    k = min(n + 2, len(df))          # +2: room to drop self even under ties
    nn = NearestNeighbors(n_neighbors=k).fit(X)
    _, idx = nn.kneighbors(X)

    names = df["account"].to_numpy()
    df["lookalikes"] = [
        "; ".join([names[j] for j in row if j != i][:n])
        for i, row in enumerate(idx)
    ]
    return df


def similar_accounts(df: pd.DataFrame, account: str, n: int = 5) -> pd.DataFrame:
    """Return the n nearest accounts to the given one, with distances.
    The query account itself is excluded by name/position identity."""
    d = df.reset_index(drop=True)
    X = StandardScaler().fit_transform(d[SIGNALS])

    matches = d.index[d["account"] == account]
    if len(matches) == 0:
        return pd.DataFrame()
    i = int(matches[0])

    k = min(n + 2, len(d))
    nn = NearestNeighbors(n_neighbors=k).fit(X)
    dist, idx = nn.kneighbors(X[i].reshape(1, -1))

    pairs = [(dst, j) for dst, j in zip(dist[0], idx[0]) if j != i][:n]
    out = d.iloc[[j for _, j in pairs]][
        ["account", "industry", "base_score", "tier"]].copy()
    out["similarity_distance"] = [round(float(dst), 2) for dst, _ in pairs]
    return out.reset_index(drop=True)
