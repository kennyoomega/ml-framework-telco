# src/pipeline/orchestrator_common.py
"""
Common orchestrator helpers (contract-level).

Policy
------
- Do NOT depend on internal implementation details of step modules.
- Only depend on stable contracts:
  - ModuleReport v1 schema
  - artifact naming + resolve_artifact_path/write_json
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
import inspect

import pandas as pd

from src.pipeline.reporting import build_module_report, finalize_module_report, make_artifact_ref
from src.utils.artifact_utils import resolve_artifact_path, write_json


ModuleFn = Callable[..., Any]


@dataclass(frozen=True)
class ModuleSpec:
    """
    A single orchestrated module.

    kind:
      - "source": produces df (e.g., ingestion)
      - "df": consumes df
      - "agg": consumes artifacts/reports

    returns_df:
      - True: fn returns (df_new, report) OR df
      - False: fn returns report
    """
    step_id: str
    name: str
    fn: Optional[ModuleFn]
    cfg_key: str
    artifact_stage: str
    artifact_name: Optional[str] = None
    enabled: bool = True
    kind: str = "df"  # "source" | "df" | "agg"
    gate_default: str = "soft"  # "hard" | "soft"
    returns_df: bool = False


def validate_module_spec(spec: ModuleSpec, tag: str) -> None:
    """Validate spec fields early to avoid silent orchestration bugs."""
    if not isinstance(spec.step_id, str) or not spec.step_id.strip():
        raise ValueError(f"[{tag}] ModuleSpec.step_id must be a non-empty string")
    if not isinstance(spec.name, str) or not spec.name.strip():
        raise ValueError(f"[{tag}] ModuleSpec.name must be a non-empty string")
    if not isinstance(spec.cfg_key, str) or not spec.cfg_key.strip():
        raise ValueError(f"[{tag}] ModuleSpec.cfg_key must be a non-empty string")
    if spec.kind not in {"source", "df", "agg"}:
        raise ValueError(f"[{tag}] ModuleSpec.kind must be 'source'|'df'|'agg', got {spec.kind!r}")
    if spec.gate_default not in {"hard", "soft"}:
        raise ValueError(f"[{tag}] ModuleSpec.gate_default must be 'hard' or 'soft', got {spec.gate_default!r}")
    if not isinstance(spec.returns_df, bool):
        raise TypeError(f"[{tag}] ModuleSpec.returns_df must be bool")


def infer_module_status(report: Any) -> str:
    """Return normalized status from ModuleReport v1."""
    if not isinstance(report, dict):
        return "fail"

    s = report.get("status")
    if isinstance(s, str) and s.strip():
        s = s.strip().lower()
        return s if s in {"pass", "warn", "fail", "skipped"} else "fail"

    summ = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    os_ = summ.get("overall_status") if isinstance(summ, dict) else None
    if isinstance(os_, str) and os_.strip():
        os_ = os_.strip().lower()
        return os_ if os_ in {"pass", "warn", "fail", "skipped"} else "fail"

    return "fail"


def is_fail(status: str) -> bool:
    return str(status).strip().lower() == "fail"


def should_halt(*, strict: bool, gate_mode: str, status: str) -> bool:
    """Central gating: only strict+hard+fail halts."""
    if not bool(strict):
        return False
    if str(gate_mode).strip().lower() != "hard":
        return False
    return is_fail(status)


def build_missing_impl_report(
    *,
    ctx: Dict[str, Any],
    rid: str,
    tag: str,
    stage: str,
    spec: ModuleSpec,
    df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """Create a valid ModuleReport v1 when module implementation is missing."""
    rep = build_module_report(
        ctx=ctx,
        stage=stage,
        step=str(spec.step_id),
        name=str(spec.name),
        tag=tag,
        cfg_key=str(spec.cfg_key),
        enabled=True,
        df=df,
        run_id_override=str(rid),
    )

    rep["inputs"] = {"orchestrator": True, "missing_impl": True}
    rep["thresholds_used"] = {}
    rep["used_config"] = {"cfg_key": str(spec.cfg_key)}
    rep["refs"]["self"] = make_artifact_ref(
        ctx=ctx,
        stage=str(spec.artifact_stage),
        name=str(spec.artifact_name or spec.name),
        run_id=str(rid),
    )
    rep["checks"]["infra"] = {"error": "missing_step_implementation"}

    rep = finalize_module_report(
        ctx=ctx,
        report=rep,
        overall_status="fail",
        issues=["missing_step_implementation"],
        warnings=[],
        metrics={},
        notes=["missing_step_implementation"],
        df=df,
    )
    return rep


def build_exception_report(
    *,
    ctx: Dict[str, Any],
    rid: str,
    tag: str,
    stage: str,
    spec: ModuleSpec,
    err: Exception,
    df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """Create a valid ModuleReport v1 on exception (contract-safe)."""
    rep = build_module_report(
        ctx=ctx,
        stage=stage,
        step=str(spec.step_id),
        name=str(spec.name),
        tag=tag,
        cfg_key=str(spec.cfg_key),
        enabled=True,
        df=df,
        run_id_override=str(rid),
    )

    rep["inputs"] = {"orchestrator": True, "exception_fallback": True}
    rep["thresholds_used"] = {}
    rep["used_config"] = {"cfg_key": str(spec.cfg_key)}
    rep["refs"]["self"] = make_artifact_ref(
        ctx=ctx,
        stage=str(spec.artifact_stage),
        name=str(spec.artifact_name or spec.name),
        run_id=str(rid),
    )
    rep["checks"]["exception"] = {"error_type": type(err).__name__, "error_repr": repr(err)}

    rep = finalize_module_report(
        ctx=ctx,
        report=rep,
        overall_status="fail",
        issues=["module_exception"],
        warnings=[],
        metrics={},
        notes=[repr(err)],
        df=df,
    )
    return rep


def persist_artifact_safety_net(
    *,
    ctx: Dict[str, Any],
    rid: str,
    tag: str,
    spec: ModuleSpec,
    report: Dict[str, Any],
    indent: int = 2,
) -> str:
    """Persist per-module artifact as an orchestrator safety net."""
    name = str(spec.artifact_name or spec.name)
    out_path = resolve_artifact_path(
        ctx=ctx,
        stage=str(spec.artifact_stage),
        name=name,
        run_id=str(rid),
        tag=tag,
    )
    write_json(out_path, report, tag=tag, indent=int(indent))
    return str(out_path)


def call_with_supported_kwargs(fn: ModuleFn, kwargs: Dict[str, Any]) -> Any:
    """Call fn with only kwargs supported by its signature (backward-compatible)."""
    sig = inspect.signature(fn)
    allowed = set(sig.parameters.keys())
    safe_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
    return fn(**safe_kwargs)


def invoke_module(
    *,
    spec: ModuleSpec,
    df: Optional[pd.DataFrame],
    artifacts: Dict[str, Any],
    ctx: Dict[str, Any],
    rid: str,
) -> Any:
    """Invoke module by kind. Returns raw result (df/report/tuple)."""
    if spec.fn is None:
        return None

    if spec.kind == "source":
        return call_with_supported_kwargs(spec.fn, {"ctx": ctx, "run_id": rid, "artifacts": artifacts})

    if spec.kind == "agg":
        return call_with_supported_kwargs(spec.fn, {"artifacts": artifacts, "ctx": ctx, "run_id": rid, "df": df})

    return call_with_supported_kwargs(spec.fn, {"df": df, "ctx": ctx, "run_id": rid, "artifacts": artifacts})


def normalize_module_result(
    *,
    spec: ModuleSpec,
    res: Any,
    df_in: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """
    Normalize module result into:
      { "df": Optional[pd.DataFrame], "report": Optional[Dict[str,Any]] }
    """
    df_out = df_in
    report: Optional[Dict[str, Any]] = None

    if spec.returns_df:
        if (
            isinstance(res, tuple)
            and len(res) == 2
            and isinstance(res[0], pd.DataFrame)
            and isinstance(res[1], dict)
        ):
            df_out = res[0]
            report = res[1]

        elif isinstance(res, pd.DataFrame):
            df_out = res

        elif isinstance(res, dict):
            # Contract dict: {"df": ..., "report": ...}
            maybe_df = res.get("df", None)
            maybe_report = res.get("report", None)

            if isinstance(maybe_df, pd.DataFrame):
                df_out = maybe_df

            if isinstance(maybe_report, dict):
                report = maybe_report
            else:
                # If it doesn't look like a contract dict, treat the dict as a report
                # (backward-compatible with modules that return only report dict)
                if "df" not in res and "report" not in res:
                    report = res

    else:
        if isinstance(res, dict):
            report = res

    return {"df": df_out, "report": report}


def has_missing_module_report(rep: Dict[str, Any]) -> bool:
    s = rep.get("summary") or {}
    w = s.get("warnings") or []
    return isinstance(w, list) and ("missing_module_report" in w)