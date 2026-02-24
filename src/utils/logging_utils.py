# src/utils/logging_utils.py
"""
Logging utilities.

What:
  Provide standardized logger retrieval for the project.

Why:
  - Ensure consistent logger naming across modules.
  - Avoid ad-hoc logging.getLogger() usage.
  - Make it easy to inject or override loggers in notebooks and pipelines.
"""

from __future__ import annotations

import logging
from typing import Optional


DEFAULT_LOGGER_NAME = "churn_pipeline"


def get_logger(
    logger: Optional[logging.Logger] = None,
    name: str = DEFAULT_LOGGER_NAME,
) -> logging.Logger:
    """
    Return a logger instance.

    If a logger is explicitly provided, it is returned as-is.
    Otherwise, a logger is retrieved by name.

    Parameters
    ----------
    logger : logging.Logger, optional
        Pre-configured logger instance (e.g. injected from orchestration layer).
    name : str, default DEFAULT_LOGGER_NAME
        Logger name to retrieve when logger is not provided.

    Returns
    -------
    logging.Logger
        Logger instance to be used by the caller.
    """
    return logger if logger is not None else logging.getLogger(name)
