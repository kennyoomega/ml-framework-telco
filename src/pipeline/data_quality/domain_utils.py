# src/pipeline/data_quality/domain_utils.py
"""
Segment-level utilities.

What:
  Provide reusable helpers for computing label-based rates across segments.

Why:
  - Shared by multiple domain diagnostics (e.g. 2.6.1 core, 2.6.2 addons).
  - Enforce a stable, comparable report schema for segment-level analysis.

Policy:
  - Do NOT treat missing labels as negative. Exclude missing labels from rate calculation.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from src.utils.pandas_utils import normalize_str_series

MISSING_TOKEN = "<MISSING>"


def rate_by_segment(
    df: pd.DataFrame,
    *,
    label_col: str,
    positive_label: str,
    segment_cols: List[str],
    small_segment_min_share: float,
) -> Dict[str, Any]:
    """Compute positive rate by segment level (stable report schema)."""
    if label_col not in df.columns:
        return {"error": f"label_col '{label_col}' not found"}

    pos_key = str(positive_label).strip()
    if not pos_key:
        return {"error": "positive_label is empty after strip()"}

    y_all = normalize_str_series(df[label_col])

    # Exclude missing labels from rate computation (do NOT treat as negative)
    valid = (y_all != MISSING_TOKEN)
    n_total = int(df.shape[0])
    n_valid = int(valid.sum())
    n_missing_label = int((~valid).sum())

    if n_valid == 0:
        return {
            "error": "all_labels_missing",
            "label_col": label_col,
            "meta": {
                "n_rows_total": n_total,
                "n_rows_used": 0,
                "n_labels_missing": n_missing_label,
            },
        }

    y = y_all[valid]
    pos_mask = (y == pos_key)

    out: Dict[str, Any] = {
        "meta": {
            "label_col": label_col,
            "positive_label": pos_key,
            "n_rows_total": n_total,
            "n_rows_used": n_valid,
            "n_labels_missing": n_missing_label,
        }
    }

    for c in segment_cols:
        if c not in df.columns:
            out[c] = {"exists": False, "reason": "column_not_found"}
            continue

        g = normalize_str_series(df[c])[valid]

        tab = (
            pd.DataFrame({"segment": g, "is_pos": pos_mask})
            .groupby("segment", dropna=False)
            .agg(n=("is_pos", "size"), pos_rate=("is_pos", "mean"))
            .sort_values("pos_rate", ascending=False)
        )

        segs: Dict[str, Any] = {}
        for k, v in tab.to_dict(orient="index").items():
            n = int(v["n"])
            share = (n / n_valid) if n_valid > 0 else 0.0
            segs[str(k)] = {
                "n": n,
                "share": float(round(share, 6)),
                "positive_rate": float(round(float(v["pos_rate"]), 6)),
                "small_segment": bool(share < float(small_segment_min_share)),
            }

        out[c] = {"exists": True, "n_levels": int(tab.shape[0]), "segments": segs}

    return out


def sample_str_list(xs: List[str], *, limit: int = 10) -> List[str]:
    """Return a stable preview of a string list (for compact audit contexts)."""
    if not isinstance(xs, list):
        return []
    out = [str(x) for x in xs if isinstance(x, str) and str(x).strip()]
    return out[: max(0, int(limit))]
