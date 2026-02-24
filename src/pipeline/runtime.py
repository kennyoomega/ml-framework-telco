# src/pipeline/runtime.py
"""
Runtime context utilities.

What:
  Define and enforce the minimal runtime execution contract shared by all
  pipeline modules, including logger availability and run identity resolution.

Why:
  - Provide a single, consistent entry point for runtime validation across steps.
  - Fail fast when required execution context (logger, run_id) is missing.
  - Eliminate duplicated boilerplate checks in individual pipeline modules.
  - Standardize how run_id is resolved and propagated throughout the pipeline.

Scope:
  - Runtime-only concerns (execution context, logging, run identity).
  - No configuration loading, no validation logic, no gating decisions.

Design Notes:
  - This module is intentionally small and strict.
  - It performs validation and normalization only; it does not mutate ctx.
  - All pipeline steps are expected to call ensure_runtime_ctx() at entry.
"""

from typing import Dict, Any, Optional, Tuple


def ensure_runtime_ctx(
    *,
    ctx: Dict[str, Any],
    tag: str,
    run_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Any, str]:
    """
    Ensure minimal runtime contract for a pipeline step.

    Returns
    -------
    ctx, logger, run_id
    """
    if ctx is None or not isinstance(ctx, dict):
        raise TypeError(f"[{tag}] ctx must be a dict")

    lg = ctx.get("logger")
    if lg is None:
        raise KeyError(f"[{tag}] ctx['logger'] is required")

    rid = str(run_id or ctx.get("run_id") or "").strip()
    if not rid:
        raise ValueError(f"[{tag}] ctx['run_id'] is missing and run_id was not provided")

    return ctx, lg, rid
