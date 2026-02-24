# src/pipeline/data_integrity/row_identity.py

from __future__ import annotations

from typing import List, Sequence

import pandas as pd


_DEFAULT_MISSING_TOKEN = "__MISSING__"
_DEFAULT_SEPARATOR = "||"


def build_row_id_series(
    df: pd.DataFrame,
    id_columns: Sequence[str],
    *,
    tag: str,
    missing_token: str = _DEFAULT_MISSING_TOKEN,
    separator: str = _DEFAULT_SEPARATOR,
    name: str = "row_id",
) -> pd.Series:
    """
    Build a stable row identity Series from key columns.

    - Supports composite keys by joining parts with a stable separator.
    - Replaces missing key parts with a stable token to avoid join failures.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    id_columns : Sequence[str]
        Entity id columns (e.g., dataset.keys.primary).
    tag : str
        Tag for error messages.
    missing_token : str
        Token to replace missing key parts.
    separator : str
        Separator for composite keys.
    name : str
        Name of the returned Series.

    Returns
    -------
    pd.Series
        Row identity Series (string dtype), same length as df.
    """
    # --- 1) Input validation ---
    if df is None or not isinstance(df, pd.DataFrame):
        raise TypeError(f"[{tag}] df must be a pandas DataFrame")

    if not isinstance(tag, str) or not tag.strip():
        raise ValueError("[build_row_id_series] tag must be a non-empty string")

    if not isinstance(missing_token, str) or not missing_token.strip():
        raise ValueError(f"[{tag}] missing_token must be a non-empty string")

    if not isinstance(separator, str) or not separator:
        raise ValueError(f"[{tag}] separator must be a non-empty string")

    # --- 2) Normalize id columns (strip + drop empty + stable de-dup) ---
    cols: List[str] = []
    seen = set()
    for i, x in enumerate(list(id_columns) if id_columns is not None else []):
        if not isinstance(x, str):
            raise TypeError(f"[{tag}] id_columns[{i}] must be str, got {type(x).__name__}")
        s = x.strip()
        if not s or s in seen:
            continue
        cols.append(s)
        seen.add(s)

    if not cols:
        raise ValueError(f"[{tag}] id_columns must be a non-empty list[str] after normalization")

    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        raise KeyError(f"[{tag}] id_columns {missing_cols} not found. Available={list(df.columns)}")

    # --- 3) Build row_id (consistent missing strategy for 1-col and multi-col) ---
    if len(cols) == 1:
        s = df[cols[0]].astype("string")
        out = s.where(s.notna(), other=missing_token)
        out.name = name
        return out

    tmp = df[cols].astype("string")
    tmp = tmp.where(tmp.notna(), other=missing_token)
    out = tmp.agg(separator.join, axis=1)
    out = out.astype("string")
    out.name = name
    return out