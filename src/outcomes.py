"""Engagement outcomes: the ground truth the model learns from.

Every logged outcome (Won / Engaged / No Response / Lost) is a labelled
example. Once enough accumulate, scripts/train_weights.py fits a logistic
regression on the five signals and the learned weights replace the
hand-configured ones - the scoring model graduates from heuristic to
evidence-based, with the configured weights as the always-available
fallback.
"""

from datetime import date

import pandas as pd

from src import store


def load_outcomes() -> pd.DataFrame:
    return store.load("outcomes")


def log_outcome(account: str, outcome: str, amount: str = "",
                note: str = "", logged_by: str = "") -> None:
    store.append("outcomes", {
        "date": date.today().isoformat(),
        "account": account,
        "outcome": outcome,
        "amount": str(amount).strip(),
        "note": note.strip(),
        "logged_by": logged_by.strip() or "Unattributed",
    })


def account_outcomes(account: str) -> pd.DataFrame:
    df = load_outcomes()
    return df[df["account"] == account].sort_values("date", ascending=False)
