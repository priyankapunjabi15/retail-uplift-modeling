"""
src/data/features.py
--------------------
Feature engineering functions for the Hillstrom uplift project.
"""

import pandas as pd
import numpy as np


def encode_channel(df: pd.DataFrame) -> pd.DataFrame:
    """
    One-hot encode the 'channel' column (nominal — no ordering).
    Drops original 'channel' column to avoid redundancy.
    """
    df = df.copy()
    dummies = pd.get_dummies(df["channel"], prefix="channel", dtype=np.int8)
    dummies.columns = dummies.columns.str.lower().str.replace(" ", "_")
    df = pd.concat([df, dummies], axis=1)
    df = df.drop(columns=["channel"])
    return df


def encode_zip_code(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordinal-encode zip_code by population density: Rural=0, Suburban=1, Urban=2.
    Keeps original as 'zip_code_original'. Falls back to -1 for unmapped values.
    """
    df = df.copy()
    zip_map = {"Rural": 0, "Suburban": 1, "Urban": 2}
    df["zip_code_original"] = df["zip_code"]
    # fillna(-1) guards against any values that don't match the map keys
    df["zip_code"] = (
        df["zip_code"].map(zip_map).fillna(-1).astype(np.int8)
    )
    return df


def encode_history_segment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordinal-encode history_segment by spend tier.
    Falls back to -1 for unmapped values.
    """
    df = df.copy()
    tier_map = {
        "1) $0 - $100": 0,
        "2) $100 - $200": 1,
        "3) $200 - $350": 2,
        "4) $350 - $500": 3,
        "5) $500 - $750": 4,
        "6) $750 - $1,000": 5,
        "7) $1,000+": 6,
    }
    df["history_segment_code"] = (
        df["history_segment"].map(tier_map).fillna(-1).astype(np.int8)
    )
    return df


def add_rfm_proxies(df: pd.DataFrame) -> pd.DataFrame:
    """
    RFM-style proxy features.

    Uses labels=False in pd.qcut — this returns plain integer bin indices
    (0, 1, 2, 3) as float64 instead of a Categorical, so .fillna(0).astype(int8)
    works without any .cat.codes gymnastics.
    """
    df = df.copy()

    df["category_count"] = (
        df["mens"].fillna(0) + df["womens"].fillna(0)
    ).astype(np.int8)

    df["recency_bin"] = (
        pd.qcut(df["recency"], q=4, labels=False, duplicates="drop")
        .fillna(0)
        .astype(np.int8)
    )

    df["history_bin"] = (
        pd.qcut(df["history"], q=4, labels=False, duplicates="drop")
        .fillna(0)
        .astype(np.int8)
    )

    return df


def feature_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the full feature engineering pipeline.

    Usage:
        from src.data.features import feature_pipeline
        df_feat = feature_pipeline(df_clean)
    """
    df = encode_channel(df)
    df = encode_zip_code(df)
    df = encode_history_segment(df)
    df = add_rfm_proxies(df)
    return df