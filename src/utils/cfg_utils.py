# src/utils/cfg_utils.py
"""
Config utilities (YAML SSOT access).

Policy
------
- NO implicit config loading.
- NO filesystem I/O.
- cfg must be injected into ctx by the entrypoint (Step1 build_ctx / runner).
"""

from __future__ import annotations

from typing import Any, List, Optional, Set, Type, Dict, Tuple

import math

from src.utils.ctx_utils import require_dict


def _split_path(path: str) -> Tuple[str, ...]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"Invalid config path: {path!r}")
    return tuple(p.strip() for p in path.split(".") if p.strip())


def _get_cfg_root(ctx: Dict[str, Any], *, tag: str) -> Dict[str, Any]:
    if ctx is None or not isinstance(ctx, dict):
        raise TypeError(f"[{tag}] ctx must be a dict")

    cfg = ctx.get("cfg")
    if not isinstance(cfg, dict):
        raise KeyError(
            f"[{tag}] ctx['cfg'] missing/invalid. "
            "Config must be loaded by entrypoint (Step1 build_ctx / runner) and injected into ctx['cfg']."
        )

    return require_dict(cfg, path="ctx.cfg", tag=tag)


def get_cfg_value(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Any = None,
    required: bool = False,
    expected_type: Optional[Type] = None,
) -> Any:
    cfg = _get_cfg_root(ctx, tag=tag)
    keys = _split_path(path)

    cur: Any = cfg
    for k in keys:
        if not isinstance(cur, dict):
            raise TypeError(f"[{tag}] Config path '{path}' expects dict at '{k}', got: {type(cur)}")
        if k not in cur:
            if required:
                raise KeyError(f"[{tag}] Missing required config key: '{path}'")
            return default
        cur = cur.get(k)

    if cur is None:
        if required:
            raise KeyError(f"[{tag}] Required config key is None: '{path}'")
        return default

    if expected_type is not None and not isinstance(cur, expected_type):
        raise TypeError(f"[{tag}] Config key '{path}' must be {expected_type}, got: {type(cur)}")

    return cur


def get_cfg_dict(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Optional[Dict[str, Any]] = None,
    required: bool = False,
) -> Dict[str, Any]:
    val = get_cfg_value(
        ctx,
        path,
        tag=tag,
        default=default if default is not None else {},
        required=required,
        expected_type=dict,
    )
    return val if isinstance(val, dict) else {}

# ----------------------------
# Normalizers (config hygiene)
# ----------------------------

def normalize_str(
    x: Any,
    *,
    tag: str,
    path: str,
    default: Optional[str] = None,
    required: bool = False,
    lower: bool = False,
    allowed: Optional[Set[str]] = None,
    strict_type: bool = True,
) -> str:
    """Normalize scalar string config value.

    - Fail fast when required and missing/blank.
    - Optional lower() and allowlist validation.
    - strict_type=True: require x is str (except None/default).
      strict_type=False: cast via str().
    """
    if x is None:
        if required and default is None:
            raise KeyError(f"[{tag}] Missing required config key: '{path}'")
        x = default

    if x is None:
        s = ""
    else:
        if strict_type and not isinstance(x, str):
            raise TypeError(f"[{tag}] {path} must be str, got {type(x).__name__}")
        s = (x if isinstance(x, str) else str(x)).strip()

    if not s:
        if required:
            raise ValueError(f"[{tag}] {path} must be a non-empty string")
        return (default or "").strip() if default is not None else ""

    if lower:
        s = s.lower()

    if allowed is not None and s not in allowed:
        raise ValueError(f"[{tag}] {path} must be one of {sorted(list(allowed))}, got {s!r}")

    return s


def normalize_str_list(
    xs: Any,
    *,
    tag: str,
    path: str,
    dedupe: bool = True,
    allow_empty: bool = True,
    min_len: int = 0,
    allowed: Optional[Set[str]] = None,
    strict_items: bool = True,
) -> List[str]:
    """Normalize list-like config value into a clean list[str].

    - Require list
    - strict_items=True: each item must be str (fail fast)
      strict_items=False: cast to str
    - Strip whitespace
    - Drop empty strings
    - Stable de-duplication (preserve order)
    - Optional allowlist validation
    - Optional length constraints
    """
    if xs is None:
        out: List[str] = []
    else:
        if not isinstance(xs, list):
            raise TypeError(f"[{tag}] {path} must be a list, got {type(xs).__name__}")

        out = []
        for i, x in enumerate(xs):
            if strict_items and not isinstance(x, str):
                raise TypeError(f"[{tag}] {path}[{i}] must be str, got {type(x).__name__}")
            s = x.strip() if isinstance(x, str) else str(x).strip()
            if not s:
                continue
            out.append(s)

    if dedupe:
        out = list(dict.fromkeys(out))

    if not allow_empty and len(out) == 0:
        raise ValueError(f"[{tag}] {path} must be a non-empty list[str]")

    if min_len > 0 and len(out) < min_len:
        raise ValueError(f"[{tag}] {path} must have >= {min_len} items, got {len(out)}")

    if allowed is not None:
        bad = sorted([x for x in out if x not in allowed])
        if bad:
            raise ValueError(f"[{tag}] {path} contains invalid values: {bad}. allowed={sorted(list(allowed))}")

    return out


# --------------------------------
# Typed getters (preferred in steps)
# --------------------------------

def get_cfg_str(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Optional[str] = None,
    required: bool = False,
    lower: bool = False,
    allowed: Optional[Set[str]] = None,
    strict_type: bool = True,
) -> str:
    raw = get_cfg_value(ctx, path, tag=tag, default=default, required=required)
    return normalize_str(
        raw,
        tag=tag,
        path=path,
        default=default,
        required=required,
        lower=lower,
        allowed=allowed,
        strict_type=strict_type,
    )


def get_cfg_str_list(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Optional[List[str]] = None,
    required: bool = False,
    dedupe: bool = True,
    allow_empty: bool = True,
    min_len: int = 0,
    allowed: Optional[Set[str]] = None,
    strict_items: bool = True,
) -> List[str]:
    raw = get_cfg_value(
        ctx,
        path,
        tag=tag,
        default=default if default is not None else None,
        required=required,
    )
    # If required and raw is None, get_cfg_value would already raise KeyError.
    if raw is None:
        raw = default if default is not None else []
    return normalize_str_list(
        raw,
        tag=tag,
        path=path,
        dedupe=dedupe,
        allow_empty=allow_empty,
        min_len=min_len,
        allowed=allowed,
        strict_items=strict_items,
    )


def get_cfg_int(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Optional[int] = None,
    required: bool = False,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
    strict_type: bool = True,
) -> int:
    raw = get_cfg_value(ctx, path, tag=tag, default=default, required=required)

    if raw is None:
        if required and default is None:
            raise KeyError(f"[{tag}] Missing required config key: '{path}'")
        raw = default

    if strict_type and not isinstance(raw, int):
        raise TypeError(f"[{tag}] {path} must be int, got {type(raw).__name__}")
    try:
        val = int(raw)
    except Exception as e:
        raise TypeError(f"[{tag}] {path} must be int-castable, got {raw!r}") from e

    if min_value is not None and val < min_value:
        raise ValueError(f"[{tag}] {path} must be >= {min_value}, got {val}")
    if max_value is not None and val > max_value:
        raise ValueError(f"[{tag}] {path} must be <= {max_value}, got {val}")

    return val


def get_cfg_float(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Optional[float] = None,
    required: bool = False,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    strict_type: bool = True,
) -> float:
    raw = get_cfg_value(ctx, path, tag=tag, default=default, required=required)

    if raw is None:
        if required and default is None:
            raise KeyError(f"[{tag}] Missing required config key: '{path}'")
        raw = default

    if strict_type and not isinstance(raw, (int, float)):
        raise TypeError(f"[{tag}] {path} must be float, got {type(raw).__name__}")

    try:
        val = float(raw)
    except Exception as e:
        raise TypeError(f"[{tag}] {path} must be float-castable, got {raw!r}") from e

    if not math.isfinite(val):
        raise ValueError(f"[{tag}] {path} must be finite, got {val}")

    if min_value is not None and val < min_value:
        raise ValueError(f"[{tag}] {path} must be >= {min_value}, got {val}")
    if max_value is not None and val > max_value:
        raise ValueError(f"[{tag}] {path} must be <= {max_value}, got {val}")

    return val


def get_cfg_bool(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Optional[bool] = None,
    required: bool = False,
    strict_type: bool = True,
) -> bool:
    """Typed getter for boolean config values.

    strict_type=True:
      - Only accept real bool.
    strict_type=False:
      - Accept bool/int(0/1)/str(true/false/1/0/yes/no/on/off).
    """
    raw = get_cfg_value(ctx, path, tag=tag, default=default, required=required)

    if raw is None:
        if required and default is None:
            raise KeyError(f"[{tag}] Missing required config key: '{path}'")
        raw = default

    if isinstance(raw, bool):
        return raw

    if strict_type:
        raise TypeError(f"[{tag}] {path} must be bool, got {type(raw).__name__}")

    # Non-strict parsing
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)

    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in {"true", "1", "yes", "y", "on"}:
            return True
        if s in {"false", "0", "no", "n", "off"}:
            return False

    raise TypeError(f"[{tag}] {path} must be bool-castable, got {raw!r}")


def get_cfg_float_list(
    ctx: Dict[str, Any],
    path: str,
    *,
    tag: str = "CFG",
    default: Optional[List[float]] = None,
    required: bool = False,
    allow_empty: bool = True,
    min_len: int = 0,
    max_len: Optional[int] = None,
    strict_items: bool = True,
    finite: bool = True,
    dedupe: bool = False,
    sort_unique: bool = False,
) -> List[float]:
    """Typed getter for list[float] config values.

    strict_items=True:
      - Each item must be int/float (fail fast).
    strict_items=False:
      - Try float(x) for each item.
    """
    raw = get_cfg_value(
        ctx,
        path,
        tag=tag,
        default=default if default is not None else None,
        required=required,
    )

    if raw is None:
        raw = default if default is not None else []

    if not isinstance(raw, list):
        raise TypeError(f"[{tag}] {path} must be a list, got {type(raw).__name__}")

    out: List[float] = []
    for i, x in enumerate(raw):
        if strict_items and not isinstance(x, (int, float)):
            raise TypeError(f"[{tag}] {path}[{i}] must be number, got {type(x).__name__}")
        try:
            v = float(x)
        except Exception as e:
            raise TypeError(f"[{tag}] {path}[{i}] must be float-castable, got {x!r}") from e

        if finite and not math.isfinite(v):
            raise ValueError(f"[{tag}] {path}[{i}] must be finite, got {v}")

        out.append(v)

    if dedupe:
        # stable dedupe
        seen = set()
        out2: List[float] = []
        for v in out:
            if v in seen:
                continue
            seen.add(v)
            out2.append(v)
        out = out2

    if sort_unique:
        out = sorted(set(out))

    if not allow_empty and len(out) == 0:
        raise ValueError(f"[{tag}] {path} must be a non-empty list[float]")

    if min_len > 0 and len(out) < min_len:
        raise ValueError(f"[{tag}] {path} must have >= {min_len} items, got {len(out)}")

    if max_len is not None and len(out) > max_len:
        raise ValueError(f"[{tag}] {path} must have <= {max_len} items, got {len(out)}")

    return out