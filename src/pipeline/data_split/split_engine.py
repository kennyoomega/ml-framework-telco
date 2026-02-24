# src/pipeline/data_split/split_engine.py
"""
Pure split engine — no ctx, no YAML, no logging.

What:
  Provide reproducible train/val/test or CV fold assignment
  for tabular DataFrames.

Why:
  Isolate split logic from pipeline orchestration so it can be
  tested and reused independently (same pattern as cleaning_engine.py).

Design:
  - Input:  df + explicit params (no YAML reads)
  - Output: (split_df, engine_report)
      split_df:      original index + column "split" ∈ {train, val, test}
      engine_report: metadata dict (shapes, strategy, random_state, etc.)
  - No side effects (no file I/O, no logging)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, StratifiedShuffleSplit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_label(series: pd.Series, positive_label: Optional[str]) -> pd.Series:
    """Return a binary int series (1=positive, 0=negative) for stratification."""
    if positive_label is not None:
        pos = str(positive_label).strip()
        return series.astype(str).str.strip().eq(pos).astype(int)
    # Fallback: use series as-is (numeric labels)
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def _positive_rate(y: pd.Series) -> float:
    n = len(y)
    if n == 0:
        return 0.0
    return float(y.sum() / n)


# ---------------------------------------------------------------------------
# Public API — Holdout
# ---------------------------------------------------------------------------

def build_holdout_split(
    df: pd.DataFrame,
    *,
    label_col: str,
    positive_label: Optional[str] = None,
    strategy: str = "stratified",
    test_size: float = 0.20,
    val_size: float = 0.20,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Build a reproducible holdout split (train / val / test).

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame (must contain label_col).
    label_col : str
        Name of the target/label column.
    positive_label : Optional[str]
        String value of the positive class (used for stratification reporting).
    strategy : str
        "stratified" — preserves label distribution in each split.
        "random"     — simple random split (ignores label distribution).
    test_size : float
        Fraction of the full dataset for the test set (e.g. 0.20 → 20%).
    val_size : float
        Fraction of the full dataset for the val set (e.g. 0.20 → 20%).
        Engine converts to val_size_of_trainval = val_size / (1 - test_size).
    random_state : int
        RNG seed for reproducibility.

    Returns
    -------
    split_df : pd.DataFrame
        Index-aligned DataFrame with a single column "split"
        containing values "train", "val", or "test".
    engine_report : dict
        Metadata: split counts, positive rates, strategy, random_state.

    Raises
    ------
    ValueError
        On invalid parameters or insufficient data.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"[SPLIT_ENGINE] df must be pd.DataFrame, got {type(df)}")
    if label_col not in df.columns:
        raise ValueError(f"[SPLIT_ENGINE] label_col '{label_col}' not in df.columns")
    if not (0 < test_size < 1):
        raise ValueError(f"[SPLIT_ENGINE] test_size must be in (0,1), got {test_size}")
    if not (0 < val_size < 1):
        raise ValueError(f"[SPLIT_ENGINE] val_size must be in (0,1), got {val_size}")
    if test_size + val_size >= 1.0:
        raise ValueError(
            f"[SPLIT_ENGINE] test_size ({test_size}) + val_size ({val_size}) >= 1.0"
        )

    strategy_l = str(strategy).strip().lower()
    if strategy_l not in {"stratified", "random"}:
        raise ValueError(
            f"[SPLIT_ENGINE] strategy must be 'stratified' or 'random', got '{strategy}'"
        )

    n_total = len(df)
    y_raw = df[label_col]
    y_enc = _normalize_label(y_raw, positive_label)

    # Drop rows with missing labels for split indexing
    valid_mask = y_raw.notna()
    idx_valid = df.index[valid_mask]
    y_valid = y_enc.loc[idx_valid]

    n_valid = len(idx_valid)
    if n_valid < 3:
        raise ValueError(
            f"[SPLIT_ENGINE] Need at least 3 non-missing label rows, got {n_valid}"
        )

    # --- Step 1: separate test from (train+val) ---
    val_size_of_trainval = val_size / (1.0 - test_size)
    stratify_arg = y_valid if strategy_l == "stratified" else None

    try:
        idx_trainval, idx_test = train_test_split(
            idx_valid,
            test_size=test_size,
            random_state=random_state,
            shuffle=True,
            stratify=stratify_arg,
        )
    except ValueError as e:
        # Fallback to random if stratification fails (e.g. very rare class)
        idx_trainval, idx_test = train_test_split(
            idx_valid,
            test_size=test_size,
            random_state=random_state,
            shuffle=True,
            stratify=None,
        )
        strategy_used = "random_fallback"
        fallback_reason = str(e)
    else:
        strategy_used = strategy_l
        fallback_reason = None

    # --- Step 2: separate val from train ---
    y_trainval = y_valid.loc[idx_trainval]
    stratify_arg2 = y_trainval if strategy_l == "stratified" else None

    try:
        idx_train, idx_val = train_test_split(
            idx_trainval,
            test_size=val_size_of_trainval,
            random_state=random_state + 1,
            shuffle=True,
            stratify=stratify_arg2,
        )
    except ValueError:
        idx_train, idx_val = train_test_split(
            idx_trainval,
            test_size=val_size_of_trainval,
            random_state=random_state + 1,
            shuffle=True,
            stratify=None,
        )
        if strategy_used != "random_fallback":
            strategy_used = "random_fallback_val"
            fallback_reason = "stratification failed on train/val split"

    # --- Build split_df (full index, NaN for missing-label rows) ---
    split_series = pd.Series(index=df.index, dtype="object", name="split")
    split_series.loc[idx_train] = "train"
    split_series.loc[idx_val] = "val"
    split_series.loc[idx_test] = "test"
    # Rows with missing labels get "excluded"
    split_series.loc[~valid_mask] = "excluded"

    split_df = split_series.to_frame()

    # --- Engine report ---
    n_train = len(idx_train)
    n_val = len(idx_val)
    n_test = len(idx_test)
    n_excluded = int((~valid_mask).sum())

    engine_report: Dict[str, Any] = {
        "split_type": "holdout",
        "strategy_requested": str(strategy),
        "strategy_used": strategy_used,
        "fallback_reason": fallback_reason,
        "random_state": int(random_state),
        "test_size_requested": float(test_size),
        "val_size_requested": float(val_size),
        "val_size_of_trainval_computed": float(round(val_size_of_trainval, 6)),
        "n_total": int(n_total),
        "n_valid": int(n_valid),
        "n_excluded": int(n_excluded),
        "n_train": int(n_train),
        "n_val": int(n_val),
        "n_test": int(n_test),
        "pct_train": float(round(n_train / n_total, 4)) if n_total > 0 else 0.0,
        "pct_val": float(round(n_val / n_total, 4)) if n_total > 0 else 0.0,
        "pct_test": float(round(n_test / n_total, 4)) if n_total > 0 else 0.0,
        "positive_rate_overall": float(round(_positive_rate(y_enc.loc[valid_mask]), 4)),
        "positive_rate_train": float(round(_positive_rate(y_enc.loc[idx_train]), 4)),
        "positive_rate_val": float(round(_positive_rate(y_enc.loc[idx_val]), 4)),
        "positive_rate_test": float(round(_positive_rate(y_enc.loc[idx_test]), 4)),
    }

    return split_df, engine_report
