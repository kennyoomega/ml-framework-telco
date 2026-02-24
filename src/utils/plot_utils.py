# src/utils/plot_utils.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence, Tuple, Optional, Any

import pandas as pd
import matplotlib.pyplot as plt


def save_current_figure(path: Path, *, dpi: int = 150) -> None:
    """Save current matplotlib figure and close (no seaborn dependency)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close()


def plot_histogram(
    series: pd.Series,
    *,
    title: str,
    xlabel: str,
    out_path: Path,
    bins: int = 30,
) -> None:
    """Plot a simple histogram."""
    x = pd.to_numeric(series, errors="coerce")
    plt.figure(figsize=(8, 4))
    plt.hist(x.dropna().to_numpy(), bins=bins)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("count")
    save_current_figure(out_path)


def plot_bar_mean(
    df: pd.DataFrame,
    *,
    group_col: str,
    value_col: str,
    title: str,
    out_path: Path,
    observed: bool = False
) -> None:
    """Plot mean(value_col) grouped by group_col (bar chart)."""
    if group_col not in df.columns or value_col not in df.columns:
        return

    g = (
        df[[group_col, value_col]]
        .dropna()
        .groupby(group_col, observed=observed)[value_col]
        .mean()
        .sort_values(ascending=False)
    )

    plt.figure(figsize=(7, 4))
    plt.bar(g.index.astype(str), g.values)
    plt.title(title)
    plt.ylabel("rate")
    plt.xticks(rotation=30, ha="right")
    save_current_figure(out_path)


def plot_bar_pairs(
    pairs: Sequence[Tuple[str, float]],
    *,
    title: str,
    ylabel: str,
    out_path: Path,
    top_n: int = 10,
    sort_desc: bool = True,
    rotate_xticks: int = 30,
) -> None:
    """Plot a simple bar chart from (label, value) pairs with optional Top-N filtering."""
    if not pairs:
        return

    # Filter invalid and coerce to float
    clean: List[Tuple[str, float]] = []
    for k, v in pairs:
        try:
            clean.append((str(k), float(v)))
        except Exception:
            continue

    if not clean:
        return

    clean = sorted(clean, key=lambda x: x[1], reverse=bool(sort_desc))
    if top_n is not None and top_n > 0:
        clean = clean[: int(top_n)]

    labels = [k for k, _ in clean]
    values = [v for _, v in clean]

    plt.figure(figsize=(8, 4))
    plt.bar(labels, values)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=rotate_xticks, ha="right")
    save_current_figure(out_path)


def plot_bar_counter(
    counter: dict,
    *,
    title: str,
    ylabel: str,
    out_path: Path,
    top_n: int = 20,
) -> None:
    """Plot a bar chart from a counter-like dict {key: count}."""
    if not isinstance(counter, dict) or not counter:
        return
    pairs = [(str(k), float(v)) for k, v in counter.items()]
    plot_bar_pairs(pairs, title=title, ylabel=ylabel, out_path=out_path, top_n=top_n)
