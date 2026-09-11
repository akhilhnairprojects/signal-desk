"""Learn signal weights from logged engagement outcomes.

Fits a logistic regression: five standardised demand signals in,
positive-outcome probability out. The normalised (non-negative)
coefficients become the scoring weights, written to
results/learned_weights.json - which scoring picks up automatically on the
next pipeline run (config.USE_LEARNED_WEIGHTS).

Guardrails: refuses to train on too little data, needs both positive and
negative examples, clips anti-predictive coefficients at zero, and always
leaves the configured weights as the fallback.

Usage: python scripts/train_weights.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from src import config, ingest, outcomes, scoring

SIGNALS = list(config.SIGNAL_WEIGHTS)
OUT_PATH = config.RESULTS_DIR / "learned_weights.json"


def main() -> None:
    logged = outcomes.load_outcomes()
    logged = logged[logged["outcome"].isin(config.OUTCOME_TYPES)]
    df = ingest.load_accounts()
    data = logged.merge(df[["account", *SIGNALS]], on="account", how="inner")

    y = data["outcome"].isin(config.POSITIVE_OUTCOMES).astype(int)
    n_pos, n_neg = int(y.sum()), int((1 - y).sum())
    if (len(data) < config.TRAIN_MIN_OUTCOMES
            or min(n_pos, n_neg) < config.TRAIN_MIN_PER_CLASS):
        print(f"Not enough signal yet: {len(data)} usable outcomes "
              f"({n_pos} positive / {n_neg} negative). Training needs "
              f">={config.TRAIN_MIN_OUTCOMES} total and "
              f">={config.TRAIN_MIN_PER_CLASS} per class. Keep logging "
              "outcomes in the Account Explorer - the dataset builds "
              "itself.")
        return

    X = StandardScaler().fit_transform(data[SIGNALS])
    model = LogisticRegression(max_iter=1000).fit(X, y)
    auc = roc_auc_score(y, model.predict_proba(X)[:, 1])

    coefs = np.clip(model.coef_[0], 0, None)
    if coefs.sum() == 0:
        print("All coefficients non-positive - signals carry no usable "
              "pattern yet. Keeping configured weights.")
        return
    weights = {s: round(float(c / coefs.sum()), 3)
               for s, c in zip(SIGNALS, coefs)}

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "weights": weights,
        "n_outcomes": len(data), "positives": n_pos, "negatives": n_neg,
        "train_auc": round(float(auc), 3),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))

    print(f"Learned weights from {len(data)} outcomes "
          f"(train AUC {auc:.2f}):")
    for s in SIGNALS:
        print(f"  {config.SIGNAL_LABELS[s]:<18} configured "
              f"{config.SIGNAL_WEIGHTS[s]:.2f} -> learned {weights[s]:.2f}")
    print(f"Saved to {OUT_PATH}. The next pipeline run scores with these; "
          "delete the file to revert to configured weights.")


if __name__ == "__main__":
    main()
