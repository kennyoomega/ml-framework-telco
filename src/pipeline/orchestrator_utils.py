# src/pipeline/orchestrator_utils.py
"""
Orchestrator config utilities.

Policy
------
- Read from ctx['cfg'] (SSOT).
- No ctx['pipeline'] shortcut dependency.
"""

from __future__ import annotations

from typing import Any, Dict

from src.utils.cfg_utils import get_cfg_dict, get_cfg_value


def get_stage_cfg(ctx: Dict[str, Any], stage: str, tag: str) -> Dict[str, Any]:
    """
    Read a pipeline stage config from ctx['cfg'].

    Expects
    -------
    pipeline:
      orchestrator:
        stages:
          <stage>:
            ...
    """
    stage_cfg = get_cfg_dict(ctx, f"pipeline.orchestrator.stages.{stage}", tag=tag, required=True)
    return stage_cfg


def get_gate_mode(ctx: Dict[str, Any], stage: str, gate_name: str, tag: str) -> str:
    """
    Resolve gate mode ("hard"/"soft") for a given stage gate.

    Priority
    --------
    1) pipeline.orchestrator.stages.<stage>.gates[gate_name]
    2) pipeline.gate_policy.default

    Strict Policy
    -------------
    - If strict=true and a gate is missing, raise.
    - Otherwise fallback to default.
    """
    strict = bool(get_cfg_value(ctx, "pipeline.gate_policy.strict", tag=tag, default=True))
    default_mode = str(get_cfg_value(ctx, "pipeline.gate_policy.default", tag=tag, default="soft")).lower()
    if default_mode not in {"hard", "soft"}:
        raise ValueError(f"[{tag}] pipeline.gate_policy.default must be 'hard' or 'soft'")

    stage_cfg = get_stage_cfg(ctx, stage, tag)
    gates = stage_cfg.get("gates") or {}
    if not isinstance(gates, dict):
        raise TypeError(f"[{tag}] pipeline.orchestrator.stages.{stage}.gates must be a dict")

    if gate_name not in gates:
        if strict:
            raise KeyError(f"[{tag}] Missing gate policy: pipeline.orchestrator.stages.{stage}.gates.{gate_name}")
        return default_mode

    mode = str(gates[gate_name]).lower()
    if mode not in {"hard", "soft"}:
        raise ValueError(f"[{tag}] Invalid gate mode for {stage}.{gate_name}: {mode}")

    return mode

def get_stage_steps(ctx: Dict[str, Any], stage: str, tag: str) -> list:
    """Return orchestrator steps list for a stage."""
    stage_cfg = get_stage_cfg(ctx, stage, tag)
    steps = stage_cfg.get("steps") or []
    if not isinstance(steps, list):
        raise TypeError(f"[{tag}] pipeline.orchestrator.stages.{stage}.steps must be a list")
    return steps
