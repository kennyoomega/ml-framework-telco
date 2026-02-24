# src/pipeline/reporting.py
"""
Module report utilities (ModuleReport v1).

What:
  Provide a single, stable report schema for all pipeline modules
  (e.g. data_quality 2.1–2.9, data_integrity 3.x), ensuring every module
  emits a consistent, orchestrator-friendly JSON artifact.

Why:
  - Guarantee a fixed interface for orchestrators by enforcing a strict
    module-level report contract (via YAML SSOT: pipeline.reporting).
  - Enable fail-fast validation of report structure and types, preventing
    downstream failures caused by missing keys or inconsistent schemas.
  - Centralize report finalization logic (status mirroring, summary merging,
    size limits) to keep module core logic minimal and focused.
  - Improve reproducibility and traceability through standardized run identity,
    module identity (cfg_key), resolved thresholds, and cross-artifact references.
  - Prevent report artifact bloat by truncating previews and example payloads
    according to global reporting limits.

Notes:
  - Gate decisions (hard / soft / strict / halt) are handled exclusively by
    the orchestrator layer, not by this module.
  - Business or domain validation logic belongs to individual module
    implementations (e.g. contract, health, semantic, domain diagnostics).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.utils.cfg_utils import get_cfg_dict, get_cfg_value

CFG_TAG = "REPORTING"


# ----------------------------
# Public API
# ----------------------------

def build_module_report(
    *,
    ctx: Dict[str, Any],
    stage: str,
    step: str,
    name: str,
    tag: str,
    cfg_key: str,
    enabled: bool,
    df: Optional[Any] = None,
    run_id_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build ModuleReport v1 skeleton.

    Notes
    -----
    - No gating logic here. Orchestrator computes gates.
    - The returned report always includes all required keys (even if empty).
    - total_rows/total_cols are derived from df.shape if df is provided.
    """
    _require_non_empty_str(stage, "stage")
    _require_non_empty_str(step, "step")
    _require_non_empty_str(name, "name")
    _require_non_empty_str(tag, "tag")
    _require_non_empty_str(cfg_key, "cfg_key")

    cfg = _get_reporting_cfg(ctx)
    schema_version = int(cfg.get("schema_version", 1))

    rid = _resolve_run_id(ctx, run_id_override=run_id_override)
    n_rows, n_cols = _infer_shape(df)

    report: Dict[str, Any] = {
        "schema_version": schema_version,
        "run_id": str(rid),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "module": {
            "stage": str(stage),
            "step": str(step),
            "name": str(name),
            "tag": str(tag),
            "cfg_key": str(cfg_key),
            "enabled": bool(enabled),
        },
        "summary": {
            "total_rows": int(n_rows),
            "total_cols": int(n_cols),
            "overall_status": None,
            "issues": [],
            "warnings": [],
            "metrics": {},
            "notes": [],
        },
        "status": None,
        "inputs": {},
        "thresholds_used": {},
        "used_config": {},
        "refs": {},
        "checks": {},
    }

    # Ensure required keys exist (defensive)
    _ensure_required_top_keys(report, cfg)
    _ensure_required_nested_keys(report, cfg)

    # Optional verbosity toggles (keys still exist, but may remain empty)
    include = cfg.get("include", {}) if isinstance(cfg.get("include"), dict) else {}
    if not bool(include.get("inputs_block", True)):
        report["inputs"] = {}

    # Fail fast during development
    validate_module_report_schema(ctx=ctx, report=report)

    return report


def finalize_module_report(
    *,
    ctx: Dict[str, Any],
    report: Dict[str, Any],
    overall_status: str,
    issues: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    notes: Optional[List[str]] = None,
    df: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Finalize ModuleReport v1.

    What it does:
      - Set summary.overall_status and mirror top-level status
      - Merge issues/warnings/metrics/notes into summary
      - Apply YAML size limits (preview/examples truncation)
      - Validate schema contract again

    No gating logic (halt decisions) is performed here.
    """
    cfg = _get_reporting_cfg(ctx)
    allowed = set(cfg.get("status_values", ["pass", "warn", "fail", "skipped"]))

    status = str(overall_status).strip().lower()
    if status not in allowed:
        raise ValueError(f"[{CFG_TAG}] invalid overall_status={overall_status!r}; allowed={sorted(allowed)}")

    _ensure_required_top_keys(report, cfg)
    _ensure_required_nested_keys(report, cfg)

    # Centralize shape update (always overwrite with df if provided)
    if df is not None:
        n_rows, n_cols = _infer_shape(df)
        report["summary"]["total_rows"] = int(n_rows)
        report["summary"]["total_cols"] = int(n_cols)

    # Set status + mirror
    report["summary"]["overall_status"] = status
    report["status"] = status

    # Merge arrays and dicts into summary
    if issues:
        report["summary"]["issues"] = _merge_list(report["summary"].get("issues"), issues)
    if warnings:
        report["summary"]["warnings"] = _merge_list(report["summary"].get("warnings"), warnings)
    if metrics:
        base = report["summary"].get("metrics") if isinstance(report["summary"].get("metrics"), dict) else {}
        base.update(metrics)
        report["summary"]["metrics"] = base
    if notes:
        report["summary"]["notes"] = _merge_list(report["summary"].get("notes"), notes)

    # Apply size limits (artifact bloat protection)
    limits = cfg.get("limits", {}) if isinstance(cfg.get("limits"), dict) else {}
    _apply_limits(report, limits)

    # Final strict validation
    validate_module_report_schema(ctx=ctx, report=report)

    return report


def validate_module_report_schema(*, ctx: Dict[str, Any], report: Dict[str, Any]) -> None:
    """
    Validate ModuleReport v1 schema contract.

    Raises KeyError / TypeError / ValueError on violations.
    """
    cfg = _get_reporting_cfg(ctx)

    required_top = cfg.get("required_top_keys", [])
    if not isinstance(required_top, list):
        raise TypeError(f"[{CFG_TAG}] pipeline.reporting.required_top_keys must be list[str]")

    for k in required_top:
        if k not in report:
            raise KeyError(f"[{CFG_TAG}] missing required top-level key: {k!r}")

    # schema_version
    if not isinstance(report.get("schema_version"), int):
        raise TypeError(f"[{CFG_TAG}] schema_version must be int")

    # run_id / timestamp
    if not isinstance(report.get("run_id"), str) or not report["run_id"].strip():
        raise TypeError(f"[{CFG_TAG}] run_id must be a non-empty string")
    if not isinstance(report.get("timestamp_utc"), str) or not report["timestamp_utc"].strip():
        raise TypeError(f"[{CFG_TAG}] timestamp_utc must be a non-empty string")

    # module block
    mod = report.get("module")
    if not isinstance(mod, dict):
        raise TypeError(f"[{CFG_TAG}] module must be dict")

    mod_req = (cfg.get("module", {}) or {}).get("required_keys", [])
    if not isinstance(mod_req, list):
        raise TypeError(f"[{CFG_TAG}] pipeline.reporting.module.required_keys must be list[str]")
    for k in mod_req:
        if k not in mod:
            raise KeyError(f"[{CFG_TAG}] missing module.required key: {k!r}")

    for k in ["stage", "step", "name", "tag", "cfg_key"]:
        if not isinstance(mod.get(k), str) or not mod[k].strip():
            raise TypeError(f"[{CFG_TAG}] module.{k} must be a non-empty string")
    if not isinstance(mod.get("enabled"), bool):
        raise TypeError(f"[{CFG_TAG}] module.enabled must be bool")

    # summary block
    summ = report.get("summary")
    if not isinstance(summ, dict):
        raise TypeError(f"[{CFG_TAG}] summary must be dict")

    summ_req = (cfg.get("summary", {}) or {}).get("required_keys", [])
    if not isinstance(summ_req, list):
        raise TypeError(f"[{CFG_TAG}] pipeline.reporting.summary.required_keys must be list[str]")
    for k in summ_req:
        if k not in summ:
            raise KeyError(f"[{CFG_TAG}] missing summary.required key: {k!r}")

    if not isinstance(summ.get("total_rows"), int):
        raise TypeError(f"[{CFG_TAG}] summary.total_rows must be int")
    if not isinstance(summ.get("total_cols"), int):
        raise TypeError(f"[{CFG_TAG}] summary.total_cols must be int")
    if not isinstance(summ.get("issues"), list):
        raise TypeError(f"[{CFG_TAG}] summary.issues must be list[str]")
    if not isinstance(summ.get("warnings"), list):
        raise TypeError(f"[{CFG_TAG}] summary.warnings must be list[str]")
    if not isinstance(summ.get("metrics"), dict):
        raise TypeError(f"[{CFG_TAG}] summary.metrics must be dict")
    if not isinstance(summ.get("notes"), list):
        raise TypeError(f"[{CFG_TAG}] summary.notes must be list[str]")

    allowed = set(cfg.get("status_values", ["pass", "warn", "fail", "skipped"]))
    st = report.get("status")
    ov = summ.get("overall_status")

    if ov is not None:
        if not isinstance(ov, str) or ov not in allowed:
            raise ValueError(f"[{CFG_TAG}] summary.overall_status must be one of {sorted(allowed)} or None")
    if st is not None:
        if not isinstance(st, str) or st not in allowed:
            raise ValueError(f"[{CFG_TAG}] status must be one of {sorted(allowed)} or None")
    if st is not None and ov is not None and st != ov:
        raise ValueError(f"[{CFG_TAG}] status must mirror summary.overall_status when both are set")

    for blk in ["inputs", "thresholds_used", "used_config", "refs", "checks"]:
        if not isinstance(report.get(blk), dict):
            raise TypeError(f"[{CFG_TAG}] {blk} must be dict")

    return None


def make_artifact_ref(
    *,
    ctx: Dict[str, Any],
    stage: str,
    name: str,
    run_id: str,
) -> Dict[str, Any]:
    """
    Create a stable artifact reference.

    The ref is path-agnostic and tag-agnostic:
      {"stage": ..., "name": ..., "run_id": ..., "filename": ...}

    It uses YAML artifacts.naming.pattern when available.
    """
    _require_non_empty_str(stage, "stage")
    _require_non_empty_str(name, "name")
    _require_non_empty_str(run_id, "run_id")

    pattern = get_cfg_value(ctx, "artifacts.naming.pattern", tag=CFG_TAG, default=None, required=False, expected_type=str)
    filename = _render_artifact_filename(pattern, stage=stage, name=name, run_id=run_id)

    return {
        "stage": str(stage),
        "name": str(name),
        "run_id": str(run_id),
        "filename": filename,
    }


# ----------------------------
# Internal helpers
# ----------------------------

def _get_reporting_cfg(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read reporting config from YAML SSOT: pipeline.reporting

    Provides safe defaults if config is missing (development-friendly).
    """
    cfg = get_cfg_dict(ctx, "pipeline.reporting", tag=CFG_TAG, default={}, required=False)

    # Defaults
    cfg.setdefault("schema_version", 1)
    cfg.setdefault("status_values", ["pass", "warn", "fail", "skipped"])
    cfg.setdefault(
        "required_top_keys",
        [
            "schema_version",
            "run_id",
            "timestamp_utc",
            "module",
            "summary",
            "status",
            "inputs",
            "thresholds_used",
            "used_config",
            "refs",
            "checks",
        ],
    )
    cfg.setdefault("include", {"inputs_block": True})
    cfg.setdefault("limits", {"max_preview_rows": 3, "max_preview_cols": 5, "max_examples": 20})

    cfg.setdefault("module", {"required_keys": ["stage", "step", "name", "tag", "cfg_key", "enabled"]})
    cfg.setdefault(
        "summary",
        {"required_keys": ["total_rows", "total_cols", "overall_status", "issues", "warnings", "metrics", "notes"]},
    )

    return cfg


def _resolve_run_id(ctx: Dict[str, Any], *, run_id_override: Optional[str]) -> str:
    """Resolve run_id from override or ctx['run_id']."""
    if run_id_override is not None:
        rid = str(run_id_override).strip()
        if not rid:
            raise ValueError(f"[{CFG_TAG}] run_id_override must be a non-empty string if provided")
        return rid

    rid = ctx.get("run_id")
    rid = str(rid).strip() if rid is not None else ""
    if not rid:
        raise KeyError(f"[{CFG_TAG}] ctx['run_id'] is required for reporting")
    return rid


def _infer_shape(df: Optional[Any]) -> Tuple[int, int]:
    """Infer (n_rows, n_cols) from df.shape if available."""
    if df is None:
        return 0, 0
    shp = getattr(df, "shape", None)
    if shp is None:
        return 0, 0
    try:
        return int(shp[0]), int(shp[1])
    except Exception:
        return 0, 0


def _ensure_required_top_keys(report: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    """Defensively ensure required top-level keys exist."""
    required = cfg.get("required_top_keys", [])
    if not isinstance(required, list):
        return

    for k in required:
        if k in report:
            continue
        if k in {"module", "summary", "inputs", "thresholds_used", "used_config", "refs", "checks"}:
            report[k] = {}
        elif k in {"run_id", "timestamp_utc", "status"}:
            report[k] = None
        elif k == "schema_version":
            report[k] = int(cfg.get("schema_version", 1))
        else:
            report[k] = None


def _ensure_required_nested_keys(report: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    """Defensively ensure module/summary required keys exist."""
    if not isinstance(report.get("module"), dict):
        report["module"] = {}
    if not isinstance(report.get("summary"), dict):
        report["summary"] = {}

    mod_req = (cfg.get("module", {}) or {}).get("required_keys", [])
    if isinstance(mod_req, list):
        for k in mod_req:
            report["module"].setdefault(k, None)

    summ_req = (cfg.get("summary", {}) or {}).get("required_keys", [])
    if isinstance(summ_req, list):
        for k in summ_req:
            if k in {"issues", "warnings", "notes"}:
                report["summary"].setdefault(k, [])
            elif k == "metrics":
                report["summary"].setdefault(k, {})
            else:
                report["summary"].setdefault(k, None)


def _merge_list(base: Any, extra: List[str]) -> List[str]:
    """Merge two lists of strings with de-duplication while preserving order."""
    out: List[str] = []

    if isinstance(base, list):
        for x in base:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())

    for x in extra:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())

    seen = set()
    deduped: List[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        deduped.append(x)

    return deduped


def _apply_limits(report: Dict[str, Any], limits: Dict[str, Any]) -> None:
    """
    Apply size limits to avoid report artifact bloat.

    Supported:
      - Truncate checks.preview (rows/cols) if present
      - Truncate any list under checks whose key contains 'examples'
    """
    if not isinstance(limits, dict):
        return

    max_preview_rows = int(limits.get("max_preview_rows", 3))
    max_preview_cols = int(limits.get("max_preview_cols", 5))
    max_examples = int(limits.get("max_examples", 20))

    checks = report.get("checks")
    if not isinstance(checks, dict):
        return

    # Preview truncation (best-effort, schema-agnostic)
    if "preview" in checks and isinstance(checks["preview"], dict):
        pv = checks["preview"]

        cols = pv.get("columns")
        rows = pv.get("rows")

        if isinstance(cols, list):
            pv["columns"] = cols[:max_preview_cols]

        if isinstance(rows, list):
            rows = rows[:max_preview_rows]
            new_rows = []
            for r in rows:
                if isinstance(r, (list, tuple)):
                    new_rows.append(list(r)[:max_preview_cols])
                elif isinstance(r, dict):
                    keys = sorted([k for k in r.keys()])
                    keep = keys[:max_preview_cols]
                    new_rows.append({k: r[k] for k in keep})
                else:
                    new_rows.append(r)
            pv["rows"] = new_rows

        checks["preview"] = pv

    # Truncate examples lists (any key containing 'examples')
    for k, v in list(checks.items()):
        if isinstance(k, str) and "examples" in k.lower() and isinstance(v, list):
            checks[k] = v[:max_examples]

    report["checks"] = checks


def _render_artifact_filename(pattern: Optional[str], *, stage: str, name: str, run_id: str) -> str:
    """Render artifact filename using a naming pattern like '{stage}_{name}_{run_id}.json'."""
    default = f"{stage}_{name}_{run_id}.json"
    if not pattern or not isinstance(pattern, str):
        return default
    try:
        return pattern.format(stage=stage, name=name, run_id=run_id)
    except Exception:
        return default


def _require_non_empty_str(val: Any, field: str) -> None:
    """Validate a required non-empty string field."""
    if not isinstance(val, str) or not val.strip():
        raise TypeError(f"[{CFG_TAG}] {field} must be a non-empty string, got: {val!r}")
