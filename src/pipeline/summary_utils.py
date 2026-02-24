# src/pipeline/summary_utils.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.path_utils import resolve_dir
from src.utils.artifact_utils import resolve_artifact_path, read_json_if_exists


def load_artifact_json(
    *,
    ctx: Dict[str, Any],
    lg,  # logging.Logger
    stage: str,
    name: str,
    run_id: str,
    tag: str,
    resolve_artifact_path_fn,  # inject to avoid circular imports in some projects
    read_json_if_exists_fn,
    legacy_filenames: Optional[List[str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Path], Dict[str, Any]]:
    """
    Load one artifact JSON:
    - SSOT path first (resolve_artifact_path)
    - fallback to legacy filenames in the same directory
    Return: (payload, path, meta)
    """
    legacy_filenames = legacy_filenames or []

    meta: Dict[str, Any] = {
        "stage": stage,
        "name": name,
        "run_id": run_id,
        "ssot_path": None,
        "loaded": False,
        "mode": None,  # "ssot" | "legacy" | None
        "path": None,
        "legacy_candidates": list(legacy_filenames),
    }

    # SSOT first
    try:
        ssot_path = resolve_artifact_path_fn(ctx=ctx, stage=stage, name=name, run_id=run_id, tag=tag)
        meta["ssot_path"] = str(ssot_path)

        payload = read_json_if_exists_fn(ssot_path, lg, tag=tag)
        if payload is not None:
            meta["loaded"] = True
            meta["mode"] = "ssot"
            meta["path"] = str(ssot_path)
            return payload, ssot_path, meta
    except Exception as e:
        lg.exception(f"[{tag}] Failed SSOT load: stage={stage}, name={name} ({e})")

    # Legacy fallback: same directory as SSOT artifacts
    if not legacy_filenames or not meta["ssot_path"]:
        return None, None, meta

    base_dir = Path(meta["ssot_path"]).parent
    for fn in legacy_filenames:
        p = base_dir / str(fn)
        payload2 = read_json_if_exists_fn(p, lg, tag=tag)
        if payload2 is not None:
            meta["loaded"] = True
            meta["mode"] = "legacy"
            meta["path"] = str(p)
            return payload2, p, meta

    return None, None, meta


def get_overall_status(report: Optional[Dict[str, Any]]) -> str:
    """Extract overall status from ModuleReport v1 and common legacy payloads."""
    if not report or not isinstance(report, dict):
        return "missing"

    s = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    if isinstance(s.get("overall_status"), str) and s.get("overall_status"):
        return str(s["overall_status"]).strip().lower()

    # legacy fallbacks
    if isinstance(report.get("validation_status"), str):
        return str(report["validation_status"]).strip().lower()
    if isinstance(report.get("status"), str):
        return str(report["status"]).strip().lower()

    return "unknown"


def get_issues(report: Optional[Dict[str, Any]]) -> List[Any]:
    """Extract issues list from ModuleReport v1 and common legacy payloads."""
    if not report or not isinstance(report, dict):
        return []

    s = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    issues = s.get("issues", None)
    if isinstance(issues, list):
        return issues

    # legacy
    fatal = report.get("fatal_issues", None)
    if isinstance(fatal, list):
        return fatal

    return []


def get_warnings(report: Optional[Dict[str, Any]]) -> List[Any]:
    """Extract warnings list from ModuleReport v1 and legacy payloads."""
    if not report or not isinstance(report, dict):
        return []

    s = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    warnings = s.get("warnings", None)
    if isinstance(warnings, list):
        return warnings

    # legacy
    w = report.get("warnings", None)
    if isinstance(w, list):
        return w

    return []


def get_metrics(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract metrics dict from ModuleReport v1 and legacy payloads."""
    if not report or not isinstance(report, dict):
        return {}

    s = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    m = s.get("metrics", None)
    if isinstance(m, dict):
        return m

    # legacy
    m2 = report.get("metrics", None)
    if isinstance(m2, dict):
        return m2

    return {}


def get_total_rows(report: Optional[Dict[str, Any]]) -> Optional[int]:
    """Extract total_rows from ModuleReport v1 or legacy payloads."""
    if not report or not isinstance(report, dict):
        return None

    s = report.get("summary", {})
    if isinstance(s, dict):
        tr = s.get("total_rows", None)
        if isinstance(tr, (int, float)) and tr >= 0:
            return int(tr)

    for k in ("n_rows", "total_rows", "rows"):
        tr = report.get(k, None)
        if isinstance(tr, (int, float)) and tr >= 0:
            return int(tr)

    hl = report.get("high_level", {})
    if isinstance(hl, dict):
        tr = hl.get("total_rows", None)
        if isinstance(tr, (int, float)) and tr >= 0:
            return int(tr)

    sb = report.get("shape_before", None)
    if isinstance(sb, (list, tuple)) and len(sb) >= 1 and isinstance(sb[0], (int, float)) and sb[0] >= 0:
        return int(sb[0])

    return None


def get_total_cols(report: Optional[Dict[str, Any]]) -> Optional[int]:
    """Extract total_cols from ModuleReport v1 or legacy payloads."""
    if not report or not isinstance(report, dict):
        return None

    s = report.get("summary", {})
    if isinstance(s, dict):
        tc = s.get("total_cols", None)
        if isinstance(tc, (int, float)) and tc >= 0:
            return int(tc)

        # legacy variants inside summary
        for k in ("total_columns", "n_cols", "cols", "total_features"):
            tc = s.get(k, None)
            if isinstance(tc, (int, float)) and tc >= 0:
                return int(tc)

    # legacy top-level variants
    for k in ("n_cols", "total_cols", "total_columns", "cols", "columns"):
        tc = report.get(k, None)
        if isinstance(tc, (int, float)) and tc >= 0:
            return int(tc)

    sb = report.get("shape_before", None)
    if isinstance(sb, (list, tuple)) and len(sb) >= 2 and isinstance(sb[1], (int, float)) and sb[1] >= 0:
        return int(sb[1])

    return None



def make_upstream_block(
    report: Optional[Dict[str, Any]],
    *,
    name: str,
    path: Optional[Path],
    meta: Dict[str, Any],
    key_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a compact upstream status block for one artifact."""
    status = get_overall_status(report)
    issues = get_issues(report)
    warnings = get_warnings(report)

    return {
        "name": str(name),
        "status": str(status),
        "n_issues": int(len(issues)),
        "n_warnings": int(len(warnings)),
        "issues": issues,
        "warnings": warnings,
        "key_metrics": key_metrics or {},
        "source_path": str(path) if path else None,
        "load_meta": meta or {},
    }


def dedupe_sorted(values: List[Any]) -> List[str]:
    """Stable, deterministic output for JSON artifacts."""
    return sorted({str(x).strip() for x in values if str(x).strip()})


def norm_status(x: Any) -> str:
    """Normalize status to a stable, lower-case string."""
    if x is None:
        return "unknown"
    s = str(x).strip().lower()
    return s if s else "unknown"


def has_non_empty_list(x: Any) -> bool:
    return isinstance(x, list) and len(x) > 0


def as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def extract_event_hints(report: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract checks.event_hints.hints[] if present (ModuleReport v1-compatible)."""
    if not isinstance(report, dict):
        return []
    checks = report.get("checks")
    if not isinstance(checks, dict):
        return []
    eh = checks.get("event_hints")
    if not isinstance(eh, dict):
        return []
    hints = eh.get("hints")
    if not isinstance(hints, list):
        return []
    out: List[Dict[str, Any]] = []
    for h in hints:
        if isinstance(h, dict):
            out.append(h)
    return out


def dedupe_event_hints(hints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupe hints by (code, evidence_path, source.module)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for h in hints:
        src = None
        if isinstance(h.get("source"), dict):
            src = h.get("source", {}).get("module")
        key = (h.get("code"), h.get("evidence_path"), src)
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def collect_upstream_event_hints(
    upstream: List[Tuple[str, Optional[Dict[str, Any]]]],
    *,
    max_hints: int = 200,
) -> List[Dict[str, Any]]:
    """
    Collect upstream hints into a single list and attach source.module for auditability.
    """
    out: List[Dict[str, Any]] = []
    for src_name, rep in upstream:
        for h in extract_event_hints(rep):
            hh = dict(h)  # shallow copy
            hh["source"] = {"module": str(src_name)}
            out.append(hh)
            if len(out) >= int(max_hints):
                return out
    return out


def find_latest_run_id_for_artifact(artifacts_dir: Path, *, stage: str, name: str) -> Optional[str]:
    """Find latest run_id for {stage}_{name}_{run_id}.json in artifacts_dir."""
    if not isinstance(stage, str) or not stage.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None

    pattern = f"{stage}_{name}_*.json"
    matches = sorted(artifacts_dir.glob(pattern))
    if not matches:
        return None

    stem = matches[-1].stem
    rid = stem.rsplit("_", 1)[-1].strip()
    return rid or None


def load_artifact_json_with_runid_fallback(
    *,
    ctx: Dict[str, Any],
    lg: Any,
    stage: str,
    name: str,
    run_id: str,
    tag: str,
    legacy_filenames: Optional[List[str]] = None,
    artifacts_dir_key: str = "outputs.artifacts",
) -> Tuple[Optional[Dict[str, Any]], Optional[Path], Dict[str, Any], str]:
    """
    Load artifact by (stage, name, run_id). If missing, fallback to latest run_id in artifacts dir.
    Returns: (report, path, meta, used_run_id).
    """
    from src.pipeline.summary_utils import load_artifact_json  # avoid circular if needed

    report, path, meta = load_artifact_json(
        ctx=ctx,
        lg=lg,
        stage=stage,
        name=name,
        run_id=str(run_id),
        tag=tag,
        resolve_artifact_path_fn=resolve_artifact_path,
        read_json_if_exists_fn=read_json_if_exists,
        legacy_filenames=legacy_filenames or [],
    )

    used_rid = str(run_id)
    if report is not None:
        return report, path, meta, used_rid

    art_dir = resolve_dir(ctx, artifacts_dir_key, required=True, tag=tag)
    latest_rid = find_latest_run_id_for_artifact(art_dir, stage=stage, name=name)
    if not latest_rid or latest_rid == used_rid:
        return report, path, meta, used_rid

    lg.warning(f"[{tag}] Upstream artifact missing for run_id={used_rid}. Fallback to latest run_id={latest_rid} for {stage}.{name}")

    legacy2: List[str] = []
    for fn in (legacy_filenames or []):
        legacy2.append(str(fn).replace(str(used_rid), str(latest_rid)))

    report2, path2, meta2 = load_artifact_json(
        ctx=ctx,
        lg=lg,
        stage=stage,
        name=name,
        run_id=str(latest_rid),
        tag=tag,
        resolve_artifact_path_fn=resolve_artifact_path,
        read_json_if_exists_fn=read_json_if_exists,
        legacy_filenames=legacy2,
    )
    return report2, path2, meta2, str(latest_rid)