# src/utils/serialization_utils.py
"""
Serialization utilities.

What:
  Provide safe, minimal helpers to convert values into JSON-serializable
  Python-native scalars.

Why:
  - NumPy scalar types (np.int64, np.float32, etc.) are not JSON-serializable.
  - Downstream artifacts (reports, manifests, metrics) must be strictly
    serializable and reproducible.
  - Centralizing scalar conversion avoids duplicated ad-hoc fixes across steps.

Design Principles:
  - Low-level, dependency-light utilities.
  - No coupling to pipeline stages or business logic.
  - Safe-by-default: invalid or non-finite values are handled explicitly.

Typical Usage:
  - Preparing artifact payloads before write_json(...)
  - Normalizing statistics in health / distribution / validation reports
"""

from typing import Any, Optional
from pathlib import Path
import numpy as np
import pandas as pd


def normalize_json_payload(value: Any) -> Any:
    """
    Recursively convert a payload into JSON-serializable Python-native types.

    Handles:
      - dict / list / tuple / set
      - numpy scalar types
      - pandas Timestamp / Timedelta
      - Path -> str

    Policy:
      - Preserve structure
      - Fail loudly on unsupported types
    """
    # --- primitive types ---
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # --- numpy scalar ---
    if isinstance(value, np.generic):
        return value.item()

    # --- pandas time types ---
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)

    # --- pathlib ---
    if isinstance(value, Path):
        return str(value)

    # --- dict ---
    if isinstance(value, dict):
        return {
            str(k): normalize_json_payload(v)
            for k, v in value.items()
        }

    # --- list / tuple / set ---
    if isinstance(value, (list, tuple, set)):
        return [normalize_json_payload(v) for v in value]

    # --- unsupported ---
    raise TypeError(f"Unsupported type for JSON serialization: {type(value)}")


def to_native_scalar(value: Any) -> Any:
    """
    Convert NumPy scalar types to native Python scalars.

    Examples:
    ---------
    np.int64(5)     -> 5
    np.float32(1.) -> 1.0

    Notes:
    ------
    - Non-NumPy values are returned unchanged.
    - This function does NOT validate finiteness or range.
    """
    if isinstance(value, np.generic):
        return value.item()
    return value


def safe_float(value: Any, *, ndigits: int = 3) -> Optional[float]:
    """
    Convert a value to a JSON-safe float.

    Policy:
    -------
    - Return None if the value is not convertible to float.
    - Return None if the value is NaN or infinite.
    - Round to a fixed number of decimal places.

    Typical Use Cases:
    ------------------
    - Summary statistics (mean, std, min, max)
    - Health / distribution reports
    - Artifact payload normalization
    """
    try:
        v = float(value)
    except Exception:
        return None

    if not np.isfinite(v):
        return None

    return float(round(v, ndigits))
