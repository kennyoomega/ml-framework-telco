# src/utils/path_utils.py
"""
Path utilities.

What:
  Provide strict, config-driven path resolution for project directories.

Why:
  - Enforce a single path convention driven by YAML (SSOT).
  - Support relative paths anchored at paths.root.
  - Fail fast when required paths are missing to avoid silent mis-writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence


def _as_path(
    x: Any,
    *,
    tag: str, 
    path: str,
) -> Path:
    """
    Convert a config value to Path.

    Raises
    ------
    TypeError
        If x cannot be interpreted as a path-like string.
    """
    if x is None:
        raise TypeError(f"[{tag}] Path value is None at '{path}'")
    try:
        return Path(str(x))
    except Exception as e:
        raise TypeError(f"[{tag}] Invalid path value at '{path}': {x!r} ({e})") from e


def get_project_root(ctx: Dict[str, Any], *, tag: str = "PATHS") -> Path:
    """
    Resolve project root from ctx["paths"]["root"].

    Raises
    ------
    KeyError
        If paths.root is missing.
    ValueError
        If root is empty.
    """
    paths = ctx.get("paths")
    if not isinstance(paths, dict):
        raise TypeError(f"[{tag}] ctx['paths'] must be a dict")

    root_val = paths.get("root")
    if root_val is None:
        raise KeyError(f"[{tag}] Missing required key: 'paths.root'")

    root = _as_path(root_val, tag=tag, path="paths.root")
    root_str = str(root).strip()
    if root_str == "":
        raise ValueError(f"[{tag}] 'paths.root' is empty")

    return root


def resolve_dir(
    ctx: Dict[str, Any],
    key: str,
    *,
    tag: str = "PATHS",
    fallback: Optional[Path] = None,
    required: bool = True,
) -> Path:
    """
    Resolve a directory path from ctx["paths"] with dotted-key support.

    Examples
    --------
    resolve_dir(ctx, "data.raw")
        -> paths.root / paths.data.raw

    resolve_dir(ctx, "outputs.artifacts")
        -> paths.root / paths.outputs.artifacts

    resolve_dir(ctx, "outputs.figures", required=False, fallback=None)
        -> None   (when not configured)

    Parameters
    ----------
    ctx : Dict[str, Any]
        Pipeline context dict.
    key : str
        Dotted key under ctx["paths"], e.g. "data.raw", "outputs.figures".
    tag : str
        Error message tag.
    fallback : Optional[Path]
        Value returned when required=False and the key is missing.
    required : bool
        If True, a missing key raises KeyError.
        If False, a missing key returns the provided fallback value.

    Returns
    -------
    Path
        Absolute path if the configured value is absolute;
        otherwise a path resolved relative to paths.root.

    Raises
    ------
    KeyError
        If required=True and the key is missing.
    TypeError
        If the paths structure or value type is invalid.
    ValueError
        If the key is empty or invalid.
    """
    root = get_project_root(ctx, tag=tag)

    paths = ctx.get("paths")
    if not isinstance(paths, dict):
        raise TypeError(f"[{tag}] ctx['paths'] must be a dict")

    parts: Sequence[str] = [p for p in key.split(".") if p.strip() != ""]
    if not parts:
        raise ValueError(f"[{tag}] key is empty")

    cur: Any = paths
    full_path = "paths." + ".".join(parts)
    for p in parts:
        if not isinstance(cur, dict):
            raise TypeError(f"[{tag}] Expected dict while traversing '{full_path}'")
        if p not in cur:
            if required:
                raise KeyError(f"[{tag}] Missing required key: '{full_path}'")
            # optional path
            return fallback
        cur = cur[p]

    pth = _as_path(cur, tag=tag, path=full_path)
    return pth if pth.is_absolute() else (root / pth)


def resolve_figures_dir(ctx: Dict[str, Any], *, tag: str = "PATHS") -> Optional[Path]:
    """
    Resolve figures directory if present.

    Policy
    ------
    - If YAML provides paths.outputs.figures -> return resolved dir.
    - Else return None (figures are optional in some steps).

    Returns
    -------
    Optional[Path]
        The resolved figures directory, or None if not configured.
    """
    return resolve_dir(ctx, "outputs.figures", tag=tag, required=False, fallback=None)
