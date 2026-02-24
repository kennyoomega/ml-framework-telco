# src/utils/ctx_utils.py
"""
Context (ctx) utilities.

What:
  Provide small, strict helpers to read from ctx/config safely.

Why:
  - Avoid silent None/default behavior that hides bugs.
  - Standardize error messages and access patterns.
  - Keep ctx/YAML as SSOT and make failures obvious ("fail fast").
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, TypeVar

T = TypeVar("T")


def require_dict(
    x: Any,
    *,
    path: str,
    tag: str,
) -> Dict[str, Any]:
    """
    Ensure the given object is a dict.

    Parameters
    ----------
    x : Any
        Object to validate.
    path : str
        Human-readable config path (e.g. "dataset.schema.dtypes").
    tag : str
        Module tag used in error messages (e.g. "CONTRACT", "INGEST").

    Returns
    -------
    Dict[str, Any]
        The same object, typed as dict.

    Raises
    ------
    TypeError
        If x is not a dict.
    """
    if not isinstance(x, dict):
        raise TypeError(f"[{tag}] Expected dict at '{path}', got: {type(x).__name__}")
    return x


def get_in(
    d: Dict[str, Any],
    keys: Sequence[str],
    *,
    path: str,
    tag: str,
) -> Any:
    """
    Retrieve a nested value from a dict using a list of keys.

    Notes
    -----
    - This is intentionally strict: missing keys or non-dict intermediate nodes raise.
    - 'path' should represent the *full* expected path for error readability.

    Parameters
    ----------
    d : Dict[str, Any]
        Root dict.
    keys : Sequence[str]
        Nested keys, e.g. ["pipeline", "data_quality", "ingestion"].
    path : str
        Human-readable expected full path, e.g. "pipeline.data_quality.ingestion".
    tag : str
        Module tag for error messages.

    Returns
    -------
    Any
        The nested value.

    Raises
    ------
    KeyError
        If any key is missing.
    TypeError
        If an intermediate node is not a dict.
    """
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            raise TypeError(
                f"[{tag}] Expected dict while traversing '{path}', "
                f"but found: {type(cur).__name__}"
            )
        if k not in cur:
            raise KeyError(f"[{tag}] Missing key '{k}' at '{path}'")
        cur = cur[k]
    return cur


def safe_get_in(
    d: Optional[Dict[str, Any]],
    dotted_path: str,
    *,
    tag: str,
    default: Any = None,
) -> Any:
    """
    Safe nested getter built on strict get_in().
    - Missing keys / wrong types -> return default (no raise)
    - dotted_path like "checks.artifacts_preview"
    """
    if not isinstance(d, dict):
        return default

    p = str(dotted_path).strip()
    if not p:
        return default

    keys: Sequence[str] = [k for k in p.split(".") if k]

    try:
        return get_in(d, keys, path=p, tag=tag)
    except Exception:
        return default


def get_run_id(ctx: Dict[str, Any], run_id: Optional[str], *, tag: str) -> str:
    """
    Resolve the effective run_id.

    Policy
    ------
    - If run_id is passed explicitly, use it.
    - Else fall back to ctx["run_id"].
    - If still missing/empty, raise (fail fast).

    Parameters
    ----------
    ctx : Dict[str, Any]
        Pipeline context dict (built from YAML + runtime values).
    run_id : str, optional
        Explicit run id override.
    tag : str
        Module tag for error messages.

    Returns
    -------
    str
        Effective run_id.

    Raises
    ------
    ValueError
        If no run_id can be resolved.
    """
    effective = run_id if run_id is not None else ctx.get("run_id")

    if effective is None:
        raise ValueError(f"[{tag}] run_id is missing (provide run_id or ctx['run_id']).")

    effective_str = str(effective).strip()
    if effective_str == "":
        raise ValueError(f"[{tag}] run_id is empty (provide a non-empty run_id).")

    return effective_str
