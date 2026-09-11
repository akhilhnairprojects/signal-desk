"""Load the baseline account universe.

Reads the Account Scoring sheet from the source workbook. Works from the
local copy in data/raw/ by default; if that file is absent and DATA_URL is
set in config.py, it pulls straight from GitHub instead. This keeps the
pipeline runnable both on a laptop and on Streamlit Cloud.
"""

import warnings

import pandas as pd

from src import config, store

# Raw workbook column -> internal column name
COLUMN_MAP = {
    "Account": "account",
    "Ticker": "ticker",
    "Industry": "industry",
    "Sub-Industry": "sub_industry",
    "AI Hiring": "ai_hiring",
    "AI Announce": "ai_announce",
    "Cloud": "cloud",
    "Global": "global_reach",
    "Data Centre": "data_centre",
    "Score": "workbook_score",
    "Tier": "workbook_tier",
    "Last Updated": "last_updated",
}


def load_accounts(path=None) -> pd.DataFrame:
    """Return the cleaned account universe as a DataFrame."""
    source = path or config.RAW_DATA_PATH
    if not str(source).startswith("http") and not config.RAW_DATA_PATH.exists():
        if config.DATA_URL:
            source = config.DATA_URL
        else:
            raise FileNotFoundError(
                f"Could not find {config.RAW_DATA_PATH}. Place accounts.xlsx "
                "in data/raw/ or set DATA_URL in src/config.py."
            )

    with warnings.catch_warnings():
        # The source workbook carries chart/formatting extensions that
        # openpyxl skips; the warnings are noise for our purposes.
        warnings.simplefilter("ignore", UserWarning)
        df = pd.read_excel(source, sheet_name="Account Scoring")

    df = df[[c for c in COLUMN_MAP if c in df.columns]].rename(columns=COLUMN_MAP)
    df = df.dropna(subset=["account"]).reset_index(drop=True)

    for col in config.SIGNAL_WEIGHTS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=list(config.SIGNAL_WEIGHTS)).reset_index(drop=True)

    df["account"] = df["account"].astype(str).str.strip()
    df = df[~df["account"].isin(config.EXCLUDED_ACCOUNTS)].reset_index(drop=True)
    df["source"] = "baseline"

    custom = store.load("custom_accounts")
    if not custom.empty:
        custom = custom.copy()
        for col in config.SIGNAL_WEIGHTS:
            custom[col] = pd.to_numeric(custom[col], errors="coerce")
        custom = custom.dropna(subset=list(config.SIGNAL_WEIGHTS))
        custom["source"] = "custom"
        custom["last_updated"] = "auto-researched " + custom["created_at"].astype(str).str[:10]
        keep = ["account", "ticker", "industry", "sub_industry",
                *config.SIGNAL_WEIGHTS, "last_updated", "source"]
        custom = custom[keep]
        # A custom row never shadows a baseline account of the same name,
        # and excluded accounts stay excluded.
        custom = custom[~custom["account"].isin(set(df["account"])
                                                | config.EXCLUDED_ACCOUNTS)]
        df = pd.concat([df, custom], ignore_index=True)
    return df

def load_baseline_only() -> pd.DataFrame:
    """The workbook universe without custom additions (for baselines)."""
    df = load_accounts()
    return df[df["source"] == "baseline"].reset_index(drop=True)
