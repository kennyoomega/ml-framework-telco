# src/utils/parse_utils.py
from __future__ import annotations

from typing import Any, Dict, List, Optional


def parse_bool(d: Dict[str, Any], key: str, default: bool = False) -> bool:
    """Parse a bool-like value from a dict with a default."""
    v = d.get(key, default)
    return bool(v)


def parse_int(
    d: Dict[str, Any],
    key: str,
    default: int,
    *,
    tag: str,
    min_value: int = 1,
    max_value: Optional[int] = None,
) -> int:
    """Parse an int from a dict with range validation."""
    v = d.get(key, default)
    try:
        iv = int(v)
    except Exception as e:
        raise TypeError(f"[{tag}] {key} must be int, got {type(v).__name__}") from e

    if iv < int(min_value):
        raise ValueError(f"[{tag}] {key} must be >= {min_value}, got {iv}")

    if max_value is not None and iv > int(max_value):
        raise ValueError(f"[{tag}] {key} must be <= {max_value}, got {iv}")

    return iv


def parse_str(d: Dict[str, Any], key: str, default: str = "") -> str:
    """Parse a stripped string from a dict with a default fallback."""
    v = d.get(key, default)
    s = str(v).strip()
    if s:
        return s
    return str(default).strip()


def parse_str_list(
    d: Dict[str, Any],
    key: str,
    default: Optional[List[str]] = None,
    *,
    tag: str,
    allow_empty: bool = False,
    dedupe: bool = True,
) -> List[str]:
    """
    Parse list[str] with normalization and optional dedupe.
    - Enforces each item is a non-empty string unless allow_empty=True.
    - Preserves order.
    """
    base = list(default) if isinstance(default, list) else []
    v = d.get(key, base)

    if v is None:
        return list(base)

    if not isinstance(v, list):
        raise TypeError(f"[{tag}] {key} must be list[str]")

    out: List[str] = []
    seen = set()

    for i, x in enumerate(v):
        if not isinstance(x, str):
            raise TypeError(f"[{tag}] {key}[{i}] must be str, got {type(x).__name__}")

        s = x.strip()
        if (not allow_empty) and (not s):
            raise ValueError(f"[{tag}] {key}[{i}] must be a non-empty string")

        if not dedupe:
            out.append(s)
            continue

        if s not in seen:
            out.append(s)
            seen.add(s)

    return out


def ensure_dict(x: Any) -> Dict[str, Any]:
    """Return x if dict else empty dict."""
    return x if isinstance(x, dict) else {}


def ensure_list(x: Any) -> List[Any]:
    """Return x if list else empty list."""
    return x if isinstance(x, list) else []
