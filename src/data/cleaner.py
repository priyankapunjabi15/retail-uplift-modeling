"""
src/data/cleaner.py
-------------------
Reusable data-cleaning functions for the Hillstrom email dataset.

Design principle: each function takes a DataFrame and returns a new
DataFrame (no in-place mutation), so the pipeline is composable and
each step is independently testable.
"""

import pandas as pd
import numpy as np


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert column names to snake_case.

    Why: The raw CSV uses mixed casing ('recency', 'history_segment',
    'mens', 'womens'). Standardizing to snake_case prevents KeyError
    bugs from typos and makes the codebase grep-friendly.
    """
    df = df.copy()
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return df


def encode_treatment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create a binary treatment column from the 'segment' column.

    Mapping:
        'Mens E-Mail'   -> treatment = 1
        'Womens E-Mail'  -> treatment = 1
        'No E-Mail'      -> treatment = 0

    Why: Uplift models need a binary treatment indicator (treated vs
    control). We collapse both email variants into one treatment group
    because our research question is "does ANY email campaign lift
    conversions?" — not "which email type works better?"

    The original 'segment' column is kept for optional sub-group analysis.
    """
    df = df.copy()
    df["treatment"] = np.where(df["segment"] == "No E-Mail", 0, 1)
    return df


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove exact duplicate rows, if any."""
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    dropped = before - len(df)
    if dropped > 0:
        print(f"[cleaner] Dropped {dropped} duplicate rows.")
    return df


def cast_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforce correct dtypes. Uses fillna(0) before int casts because
    pandas reads CSV binary columns as float64, and float->int cast
    fails if any NaN exists in the column.
    """
    df = df.copy()
    binary_cols = ["mens", "womens", "newbie", "visit", "conversion", "treatment"]
    for col in binary_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(np.int8)
    if "history" in df.columns:
        df["history"] = df["history"].fillna(0).astype(np.float32)
    if "spend" in df.columns:
        df["spend"] = df["spend"].fillna(0).astype(np.float32)
    return df


def clean_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the full cleaning pipeline in order.

    Usage:
        from src.data.cleaner import clean_pipeline
        df_clean = clean_pipeline(pd.read_csv("data/raw/hillstrom.csv"))
    """
    df = standardize_columns(df)
    df = encode_treatment(df)
    df = cast_types(df)
    return df