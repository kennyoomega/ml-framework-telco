# src/utils/pandas_utils.py
"""
Pandas utilities.

What:
  Small, strict helpers for safe Pandas Series coercion and normalization
  (numeric casting, string cleanup, explicit missing tokens).

Why:
  - Keep data coercion consistent across pipeline steps.
  - Reduce repeated boilerplate (pd.to_numeric / astype(str) / strip).
  - Make downstream reports stable and comparable by standardizing missing handling.

Policy:
  - NO filesystem I/O.
  - Operate on pd.Series only (fail fast on wrong types).
  - Missing values must be explicit when converting to strings (avoid "nan" ambiguity).
"""
from __future__ import annotations

import pandas as pd

_MISSING_TOKEN = "<MISSING>"


def normalize_str_series(
    s: pd.Series,
    *,
    missing_token: str = _MISSING_TOKEN,
    treat_empty_as_missing: bool = True,
    treat_string_nan_as_missing: bool = True,
) -> pd.Series:
    """
    Coerce Series into cleaned string categories with explicit missing token.

    - True missing (NaN/None) -> missing_token
    - Whitespace-only / empty strings -> missing_token (optional)
    - Literal strings like 'nan'/'none'/'null' -> missing_token (optional)
    """
    if not isinstance(s, pd.Series):
        raise TypeError(f"[PANDAS] normalize_str_series expects pd.Series, got {type(s).__name__}")

    mt = str(missing_token).strip()
    if not mt:
        raise ValueError("[PANDAS] missing_token must be a non-empty string")

    # 1) Start with object, keep true missing mask
    out = s.astype(object)
    is_missing = out.isna()

    # 2) Convert to str + strip (note: this turns NaN into 'nan' for non-missing entries if not masked)
    out = out.where(~is_missing, other=mt)
    out = out.astype(str).str.strip()

    # 3) Empty/whitespace -> missing_token
    if treat_empty_as_missing:
        is_empty = out.eq("")
        out = out.where(~is_empty, other=mt)

    # 4) Handle 'nan'/'none'/'null' string artifacts
    if treat_string_nan_as_missing:
        low = out.str.lower()
        is_str_missing = low.isin({"nan", "none", "null"})
        out = out.where(~is_str_missing, other=mt)

    return out

def safe_num(s: pd.Series) -> pd.Series:
    """Safely convert a Series to numeric, coercing invalid values to NaN."""
    return pd.to_numeric(s, errors="coerce")

