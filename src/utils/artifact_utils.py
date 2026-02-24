# src/utils/artifact_utils.py
"""
Artifact utilities.

What:
  Standardize artifact file paths + strict writing/reading.

Why:
  - Ensure all artifacts follow a single naming pattern (SSOT from YAML).
  - Enforce stage allowlist to prevent silent misrouting.
  - Keep artifacts reproducible and auditable across runs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.utils.path_utils import resolve_dir
from src.utils.serialization_utils import normalize_json_payload


def resolve_artifact_path(
    *,
    ctx: Dict[str, Any],
    stage: str,
    name: str,
    run_id: str,
    artifact_dir: Optional[Path] = None,
    tag: str = "ARTIFACTS",
) -> Path:
    """
    Resolve artifact path using YAML naming convention.

    YAML SSOT
    ---------
    artifacts:
      naming:
        pattern: "{stage}_{name}_{run_id}.json"
        allowed_stages: ["setup", "data_quality", "data_integrity", "experiment_tracking"]

    Policy
    ------
    - Fail fast if stage is not in allowed_stages (when provided).
    - Fail fast if required keys are missing or pattern is invalid.

    Parameters
    ----------
    ctx : Dict[str, Any]
        Pipeline context dict.
    stage : str
        Pipeline stage name, must match YAML allowed_stages.
    name : str
        Artifact logical name, e.g. "ingestion", "contract_validation".
    run_id : str
        Run identifier.
    artifact_dir : Optional[Path]
        Override output directory (mostly for tests).
    tag : str
        Error message tag.

    Returns
    -------
    Path
        Full path for the artifact file.

    Raises
    ------
    TypeError, KeyError, ValueError
        On invalid ctx, missing keys, invalid stage, or invalid pattern.
    """
    if not isinstance(ctx, dict):
        raise TypeError(f"[{tag}] ctx must be a dict")

    if not stage or stage.strip() == "":
        raise ValueError(f"[{tag}] stage is empty")
    if not name or name.strip() == "":
        raise ValueError(f"[{tag}] name is empty")
    if not run_id or run_id.strip() == "":
        raise ValueError(f"[{tag}] run_id is empty")

    cfg = ctx.get("cfg")
    if not isinstance(cfg, dict):
        raise TypeError(f"[{tag}] ctx['cfg'] must be a dict")

    artifacts_cfg = cfg.get("artifacts")
    if not isinstance(artifacts_cfg, dict):
        raise KeyError(f"[{tag}] Missing or invalid dict at: 'artifacts'")

    naming_cfg = artifacts_cfg.get("naming")
    if not isinstance(naming_cfg, dict):
        raise KeyError(f"[{tag}] Missing or invalid dict at: 'artifacts.naming'")

    pattern = naming_cfg.get("pattern")
    if not isinstance(pattern, str) or pattern.strip() == "":
        raise KeyError(f"[{tag}] Missing or invalid string at: 'artifacts.naming.pattern'")

    allowed = naming_cfg.get("allowed_stages")
    if allowed is not None:
        if not isinstance(allowed, list) or not all(isinstance(x, str) for x in allowed):
            raise TypeError(f"[{tag}] 'artifacts.naming.allowed_stages' must be a list[str]")
        if stage not in allowed:
            raise ValueError(f"[{tag}] stage '{stage}' not in allowed_stages: {allowed}")

    # Resolve artifact directory (YAML: paths.outputs.artifacts)
    out_dir = artifact_dir or resolve_dir(ctx, "outputs.artifacts", tag=tag, required=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Render filename (fail fast if placeholders mismatch)
    try:
        filename = pattern.format(stage=stage, name=name, run_id=run_id)
    except KeyError as e:
        raise ValueError(
            f"[{tag}] Invalid pattern placeholders in '{pattern}'. "
            f"Expected keys: stage, name, run_id. Missing: {e}"
        ) from e

    if Path(filename).name != filename:
        raise ValueError(f"[{tag}] pattern produced unsafe filename: {filename!r}")

    return out_dir / filename


def write_json(
    path: Path,
    payload: Dict[str, Any],
    *,
    tag: str = "ARTIFACTS",
    indent: int = 2,
) -> None:
    """
    Write JSON artifact.

    Policy
    ------
    - Ensure parent directories exist.
    - Normalize payload to JSON-safe types.
    - Fail fast on unsupported structures.
    """
    if not isinstance(payload, dict):
        raise TypeError(f"[{tag}] payload must be a dict")

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        safe_payload = normalize_json_payload(payload)
        with path.open("w", encoding="utf-8") as f:
            json.dump(safe_payload, f, indent=indent, ensure_ascii=False)
    except TypeError as e:
        raise TypeError(f"[{tag}] Payload is not JSON-serializable: {e}") from e


def read_json_if_exists(
    path: Path,
    lg: logging.Logger,
    *,
    tag: str = "ARTIFACTS",
) -> Optional[Dict[str, Any]]:
    """
    Read JSON artifact if file exists.

    Returns
    -------
    Optional[Dict[str, Any]]
        Parsed JSON dict, or None if not found or invalid.
    """
    if not path.exists():
        lg.warning(f"[{tag}] JSON not found: {path}")
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            lg.error(f"[{tag}] JSON is not a dict: {path}")
            return None
        return obj
    except Exception as e:
        lg.exception(f"[{tag}] Failed to read JSON: {path} ({e})")
        return None
