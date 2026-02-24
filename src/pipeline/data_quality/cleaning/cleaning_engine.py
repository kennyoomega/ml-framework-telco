# src/pipeline/data_quality/cleaning/cleaning_engine.py

# --- Generic Cleaning Engine (Core / Engine Layer) ---
#
# Purpose
#   Provide a reusable, config-driven cleaning engine for tabular datasets.
#
# Boundaries (MUST)
#   - Pure engine: NO ctx/YAML/SSOT access, NO project-specific assumptions.
#   - Only operates on inputs passed in (df + cleaning_config + dirs).
#
# Contract
#   Inputs:
#     df_raw: pd.DataFrame
#     cleaning_config: dict (engine schema; resolved by project runner)
#     artifact_dir/output_dir/run_id/logger
#     project_steps: optional hooks (callables) applied between generic steps
#   Outputs:
#     returns dict:
#       - df_clean (pd.DataFrame)
#       - engine_cleaning_report (dict)
#       - paths (report_path, cleaned_dataset_path)
#
# Why this split
#   Keeps cleaning logic reusable across projects while letting each project
#   define its own policy via a thin SSOT-driven runner (2.9.2).

# --- 0) Import + TAG ---
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

TAG29_E = "CLEANING_ENGINE"


# --- Internal helpers ---
def _normalize_string_columns(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Strip leading/trailing whitespace from selected string-like columns.
    If columns is None, all object/string columns are normalized.
    """
    if columns is None:
        columns = [
            col
            for col in df.columns
            if (df[col].dtype == "object" or str(df[col].dtype).startswith("string"))
        ]

    affected_cols: List[str] = []
    for col in columns:
        if col not in df.columns:
            continue
        if not (df[col].dtype == "object" or str(df[col].dtype).startswith("string")):
            continue
        df[col] = df[col].astype("string").str.strip()
        affected_cols.append(col)

    return {
        "step": "normalize_string_columns",
        "columns": affected_cols,
        "note": "Leading/trailing whitespace stripped from string-like columns.",
    }


def _drop_rows_with_missing_label(
    df: pd.DataFrame,
    label_col: str,
) -> Dict[str, Any]:
    """Drop rows where the label column is missing."""
    if label_col not in df.columns:
        return {
            "step": "drop_rows_with_missing_label",
            "label_col": label_col,
            "dropped_rows": 0,
            "note": "Label column not found; no rows dropped.",
        }

    n_before = int(df.shape[0])
    df.dropna(subset=[label_col], inplace=True)
    n_after = int(df.shape[0])

    return {
        "step": "drop_rows_with_missing_label",
        "label_col": label_col,
        "dropped_rows": int(n_before - n_after),
        "rows_before": int(n_before),
        "rows_after": int(n_after),
    }


def _cast_numeric_columns(
    df: pd.DataFrame,
    cast_config: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Cast selected columns to numeric and handle missing values.

    cast_config example:
    {
      "TotalCharges": {"type":"float", "errors":"coerce", "fill_strategy":"median"}
    }
    """
    details: Dict[str, Any] = {}

    for col, cfg in cast_config.items():
        if col not in df.columns:
            details[col] = {"note": "column_not_found"}
            continue

        target_type = str(cfg.get("type", "float")).lower().strip()

        errors = str(cfg.get("errors", "coerce")).lower().strip()
        allowed_errors = {"raise", "coerce", "ignore"}
        if errors not in allowed_errors:
            errors = "coerce"
            details.setdefault(col, {})
            details[col]["errors_note"] = "invalid_errors_value_fallback_to_coerce"

        fill_strategy = cfg.get("fill_strategy", "median")

        # Cast to numeric
        df[col] = pd.to_numeric(df[col], errors=errors)

        # Missing handling
        n_missing_before = int(df[col].isna().sum())
        fill_value: Optional[float] = None

        if fill_strategy == "median":
            v = df[col].median()
            fill_value = float(v) if pd.notna(v) else None
        elif fill_strategy == "mean":
            v = df[col].mean()
            fill_value = float(v) if pd.notna(v) else None
        elif fill_strategy == "zero":
            fill_value = 0.0
        elif fill_strategy is None:
            fill_value = None
        else:
            # Custom fixed value
            try:
                fill_value = float(fill_strategy)
            except Exception:
                fill_value = None

        if fill_value is not None:
            df[col] = df[col].fillna(fill_value)

        n_missing_after = int(df[col].isna().sum())

        details[col] = {
            "target_type": target_type,
            "error_mode": errors,
            "fill_strategy": fill_strategy,
            "missing_before": n_missing_before,
            "missing_after": n_missing_after,
            "fill_value_used": float(fill_value) if fill_value is not None else None,
        }

        # Enforce dtype
        if target_type == "float":
            df[col] = df[col].astype("float")
        elif target_type == "int":
            if int(df[col].isna().sum()) == 0:
                df[col] = df[col].astype("int")

    return {"step": "cast_numeric_columns", "columns": details}


def _apply_rare_category_bucketing(
    df: pd.DataFrame,
    columns: List[str],
    min_freq: int = 50,
    other_label: str = "Other",
) -> Dict[str, Any]:
    """Replace infrequent categories with a common label for the given columns."""
    col_reports: Dict[str, Any] = {}

    for col in columns:
        if col not in df.columns:
            col_reports[col] = {"note": "column_not_found"}
            continue

        vc = df[col].value_counts(dropna=False)
        rare_values = vc[vc < int(min_freq)].index.tolist()

        if not rare_values:
            col_reports[col] = {"note": "no_rare_categories", "min_freq": int(min_freq)}
            continue

        mask_rare = df[col].isin(rare_values)
        n_rare = int(mask_rare.sum())
        df.loc[mask_rare, col] = other_label

        col_reports[col] = {
            "min_freq": int(min_freq),
            "other_label": str(other_label),
            "n_rare_replaced": n_rare,
            "n_unique_before": int(vc.shape[0]),
            "n_unique_after": int(df[col].nunique(dropna=False)),
        }

    return {"step": "rare_category_bucketing", "columns": col_reports}


def _apply_value_mappings(
    df: pd.DataFrame,
    columns: List[str],
    mapping: Dict[Any, Any],
    *,
    include_mapping_in_report: bool = False,
) -> Dict[str, Any]:
    """
    Apply a value mapping to the selected columns.
    Example: map "No internet service" / "No phone service" to "No".
    """
    col_reports: Dict[str, Any] = {}

    for col in columns:
        if col not in df.columns:
            col_reports[col] = {"note": "column_not_found"}
            continue

        mask_affected = df[col].isin(mapping.keys())
        n_affected = int(mask_affected.sum())

        df[col] = df[col].replace(mapping)

        payload: Dict[str, Any] = {"n_affected": n_affected}
        if include_mapping_in_report:
            payload["mapping_used"] = mapping  # can be large; default off
        col_reports[col] = payload

    return {"step": "value_mappings", "columns": col_reports}


# --- 1) Public API ---
def run_generic_cleaning_engine(
    *,
    df_raw: pd.DataFrame,
    cleaning_config: Dict[str, Any],
    project_steps: Optional[List[Callable[[pd.DataFrame], Dict[str, Any]]]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Pure cleaning engine:
    - No ctx / no YAML
    - No SSOT artifact naming
    - No file I/O (caller decides persistence)

    Returns:
      (df_clean, engine_report)
    """

    if df_raw is None or not isinstance(df_raw, pd.DataFrame):
        raise TypeError(f"[{TAG29_E}] df_raw must be a pandas DataFrame")
    if not isinstance(cleaning_config, dict):
        raise TypeError(f"[{TAG29_E}] cleaning_config must be a dict")

    df = df_raw.copy()
    steps_reports: List[Dict[str, Any]] = []

    n_rows_before = int(df.shape[0])
    n_cols_before = int(df.shape[1])

    # --- Step 1: normalize strings ---
    if bool(cleaning_config.get("enable_normalize_strings", True)):
        step_report = _normalize_string_columns(df, columns=cleaning_config.get("string_columns"))
        steps_reports.append(step_report)

    # --- Step 2: drop missing label ---
    label_col = cleaning_config.get("label_col")
    if isinstance(label_col, str) and label_col.strip():
        step_report = _drop_rows_with_missing_label(df, label_col=label_col.strip())
        steps_reports.append(step_report)

    # --- Step 3: project hooks ---
    for step_fn in (project_steps or []):
        try:
            step_report = step_fn(df)
        except Exception as e:
            step_report = {
                "step": getattr(step_fn, "__name__", "project_step"),
                "error": f"{type(e).__name__}: {e}",
            }
        steps_reports.append(step_report)

    # --- Step 4: numeric cast ---
    numeric_cast_config = cleaning_config.get("numeric_cast_columns", {}) or {}
    if isinstance(numeric_cast_config, dict) and numeric_cast_config:
        step_report = _cast_numeric_columns(df, cast_config=numeric_cast_config)
        steps_reports.append(step_report)

    # --- Step 5: rare category ---
    rare_cfg = cleaning_config.get("rare_category", {}) or {}
    rare_cols = rare_cfg.get("columns", []) or []
    rare_cols = [c.strip() for c in rare_cols if isinstance(c, str) and c.strip()]
    if rare_cols:
        min_freq = int(rare_cfg.get("min_freq", 50))
        other_label = str(rare_cfg.get("other_label", "Other"))
        step_report = _apply_rare_category_bucketing(df, columns=rare_cols, min_freq=min_freq, other_label=other_label)
        steps_reports.append(step_report)

    # --- Step 6: value mappings ---
    value_map_cfg = cleaning_config.get("value_mappings", {}) or {}
    include_map = bool(cleaning_config.get("include_mapping_in_report", False))
    if isinstance(value_map_cfg, dict):
        for group_name, cfg in value_map_cfg.items():
            cfg = cfg or {}
            columns = cfg.get("columns", []) or []
            columns = [c.strip() for c in columns if isinstance(c, str) and c.strip()]
            mapping = cfg.get("mapping", {}) or {}
            if columns and mapping:
                step_report = _apply_value_mappings(
                    df,
                    columns=columns,
                    mapping=mapping,
                    include_mapping_in_report=include_map,
                )
                step_report["mapping_group"] = str(group_name)
                steps_reports.append(step_report)

    n_rows_after = int(df.shape[0])
    n_cols_after = int(df.shape[1])

    engine_report: Dict[str, Any] = {
        "high_level": {
            "rows_before": n_rows_before,
            "cols_before": n_cols_before,
            "rows_after": n_rows_after,
            "cols_after": n_cols_after,
            "steps_run": [s.get("step") for s in steps_reports],
        },
        "steps": steps_reports,
        "used_config": cleaning_config,  # ok to include; wrapper may choose to slim it
    }

    return df, engine_report