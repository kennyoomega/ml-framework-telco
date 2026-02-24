# src/utils/dataset_utils.py
"""
Dataset SSOT utilities.

Policy
------
- Read from ctx['cfg'] (SSOT).
- No filesystem I/O.
- Fail fast with clear tags.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.utils.cfg_utils import get_cfg_str, get_cfg_str_list, get_cfg_value

_ALLOWED_TASK_TYPES = {"classification", "regression"}    # Extendable


def get_label_cfg(ctx: Dict[str, Any], tag: str) -> Tuple[str, str, str]:
    """
    Read dataset label config from ctx['cfg'].

    Expects
    -------
    dataset:
      label:
        col: str
        positive: str
        task_type: str

    Returns
    -------
    (label_col, positive_label, task_type)
    """
    label_col = get_cfg_str(ctx, "dataset.label.col", tag=tag, required=True)
    positive = get_cfg_str(ctx, "dataset.label.positive", tag=tag, required=True)
    task_type = get_cfg_str(
        ctx,
        "dataset.label.task_type",
        tag=tag,
        required=True,
        lower=True,
        allowed=set(_ALLOWED_TASK_TYPES),
    )

    # get_cfg_str already enforces non-empty when required=True
    return label_col, positive, task_type


def get_schema_cols(ctx: Dict[str, Any], tag: str) -> Tuple[List[str], List[str]]:
    """
    Read dataset schema dtype column lists from ctx['cfg'].

    Expects
    -------
    dataset:
      schema:
        dtypes:
          numeric: list[str]
          categorical: list[str]

    Returns
    -------
    (numeric_cols, categorical_cols)
    """
    numeric = get_cfg_str_list(
        ctx,
        "dataset.schema.dtypes.numeric",
        tag=tag,
        required=True,
        dedupe=True,
        allow_empty=True,     # numeric list can be empty for some datasets
        strict_items=True,    # SSOT should be clean: list[str] only
    )

    categorical = get_cfg_str_list(
        ctx,
        "dataset.schema.dtypes.categorical",
        tag=tag,
        required=True,
        dedupe=True,
        allow_empty=True,
        strict_items=True,
    )

    return numeric, categorical


def get_primary_keys(ctx: Dict[str, Any], tag: str) -> List[str]:
    """
    Read dataset primary key column list from ctx['cfg'].

    Expects
    -------
    dataset:
      keys:
        primary: list[str] | str

    Returns
    -------
    list[str]
        Primary key column names (non-empty).
    """
    raw = get_cfg_value(ctx, "dataset.keys.primary", tag=tag, required=True)

    if isinstance(raw, str):
        raw_list = [raw]
    elif isinstance(raw, list):
        raw_list = raw
    else:
        raise TypeError(f"[{tag}] dataset.keys.primary must be list[str] or str, got {type(raw).__name__}")

    pks = []
    for i, x in enumerate(raw_list):
        if not isinstance(x, str):
            raise TypeError(f"[{tag}] dataset.keys.primary[{i}] must be str, got {type(x).__name__}")
        s = x.strip()
        if s:
            pks.append(s)

    # Stable de-duplication
    pks = list(dict.fromkeys(pks))

    if not pks:
        raise KeyError(f"[{tag}] dataset.keys.primary must be a non-empty list[str]")

    return pks

