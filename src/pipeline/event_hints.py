# src/pipeline/event_hints.py
from __future__ import annotations

from typing import Any, Dict, List, Optional


_ALLOWED_SEVERITY = {"hard", "fixable", "risk", "info"}


def ensure_event_hints(report: Dict[str, Any], *, version: int = 1) -> Dict[str, Any]:
    """
    Ensure report['checks']['event_hints'] exists with stable schema.

    This is policy-free: only initializes containers.
    """
    if not isinstance(report, dict):
        raise TypeError("report must be a dict")

    report.setdefault("checks", {})
    if not isinstance(report["checks"], dict):
        report["checks"] = {}

    eh = report["checks"].get("event_hints")
    if not isinstance(eh, dict):
        eh = {"version": int(version), "hints": []}
        report["checks"]["event_hints"] = eh

    # Normalize keys
    eh.setdefault("version", int(version))
    eh.setdefault("hints", [])
    if not isinstance(eh["hints"], list):
        eh["hints"] = []

    return eh


def add_event_hint(
    report: Dict[str, Any],
    *,
    code: str,
    severity_signal: str,
    evidence_path: str,
    context: Optional[Dict[str, Any]] = None,
    remediation: Optional[Dict[str, Any]] = None,
    version: int = 1,
) -> None:
    """
    Append a structured hint for downstream summarization (2.8).

    severity_signal: "hard" | "fixable" | "risk" | "info"
    evidence_path: JSON-pointer-like path within ModuleReport (stable).
    """
    eh = ensure_event_hints(report, version=version)

    sev = str(severity_signal).strip().lower()
    if sev not in _ALLOWED_SEVERITY:
        raise ValueError(f"severity_signal must be one of {_ALLOWED_SEVERITY}, got {severity_signal!r}")

    hint: Dict[str, Any] = {
        "code": str(code).strip(),
        "severity_signal": sev,
        "evidence_path": str(evidence_path).strip(),
        "context": context or {},
        "remediation": remediation or {},
    }
    eh["hints"].append(hint)


def add_event_hints_bulk(report: Dict[str, Any], hints: List[Dict[str, Any]], *, version: int = 1) -> None:
    """Append multiple hints (expects dicts shaped like add_event_hint payload)."""
    ensure_event_hints(report, version=version)
    for h in hints:
        add_event_hint(
            report,
            code=h.get("code", ""),
            severity_signal=h.get("severity_signal", "info"),
            evidence_path=h.get("evidence_path", ""),
            context=h.get("context") or {},
            remediation=h.get("remediation") or {},
            version=version,
        )
