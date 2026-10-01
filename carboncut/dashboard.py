"""Matplotlib dashboard charts (Agg backend - no display needed)."""
from __future__ import annotations

import os
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")  # headless-safe: works on servers and CI
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

COLORS = {
    "transport": "#2ca02c",  # green
    "energy": "#ff7f0e",     # orange
    "diet": "#1f77b4",       # blue
}

CATEGORY_LABELS = {
    "transport": "Transport",
    "energy": "Home energy",
    "diet": "Diet",
}


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def category_chart(by_category: dict, out_path: str,
                   title: str = "Footprint by category") -> str:
    """Bar chart of kgCO2e per category. Returns the written path."""
    cats = [c for c in ("transport", "energy", "diet") if c in by_category]
    if not cats:
        cats = sorted(by_category)
    values = np.array([by_category[c] for c in cats], dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(
        [CATEGORY_LABELS.get(c, c) for c in cats],
        values,
        color=[COLORS.get(c, "#7f7f7f") for c in cats],
        edgecolor="white",
        linewidth=1.2,
    )
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{val:.1f} kg", ha="center", va="bottom", fontsize=10,
                fontweight="bold")
    _style(ax, title, ylabel="kgCO2e")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def trend_chart(by_day: dict, out_path: str, target: float | None = None,
                title: str = "Daily footprint") -> str:
    """Per-day line chart with an optional dashed target line."""
    days = sorted(by_day)
    values = np.array([by_day[d] for d in days], dtype=float)

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.plot(days, values, marker="o", linewidth=2, color="#2ca02c",
            label="Daily kgCO2e")
    if len(values) >= 3:  # light smoothing to show the signal, not the noise
        ma = np.convolve(values, np.ones(3) / 3, mode="same")
        ax.plot(days, ma, linestyle=":", color="#1f77b4", linewidth=1.5,
                label="3-day avg")
    if target is not None:
        ax.axhline(target, linestyle="--", color="#d62728", linewidth=1.8,
                   label=f"Target {target:.1f} kg/day")
    ax.set_xticks(days[:: max(1, len(days) // 8)])
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    _style(ax, title, ylabel="kgCO2e / day")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def _fill_days(by_day: dict, days: int, end: date) -> dict:
    """Return a complete {date: kg} series for the trailing `days` window."""
    filled: dict[str, float] = {}
    for i in range(days - 1, -1, -1):
        d = (end - timedelta(days=i)).isoformat()
        filled[d] = float(by_day.get(d, 0.0))
    return filled


def render_dashboard(rows, factors, out_dir: str, days: int = 30,
                     user: str = "me", end: date | None = None) -> dict:
    """Render category + trend charts for a user's trailing window.

    The target line defaults to 90% of the first-week mean (-10% goal).
    Returns {"category": path, "trend": path, "target": float, "summary": ...}.
    """
    from .emissions import summarize

    end = end or date.today()
    summary = summarize(rows, factors)
    daily = _fill_days(summary["by_day"], days, end)

    baseline = float(np.mean(list(daily.values())[:7])) if daily else 0.0
    target = round(baseline * 0.9, 2)

    os.makedirs(out_dir, exist_ok=True)
    cat_path = os.path.join(out_dir, "dashboard_category.png")
    trend_path = os.path.join(out_dir, "dashboard_trend.png")
    category_chart(summary["by_category"], cat_path,
                   title=f"Footprint by category - {user} (last {days} days)")
    trend_chart(daily, trend_path, target=target,
                title=f"Daily footprint - {user} (target: -10% vs first week)")
    return {"category": cat_path, "trend": trend_path,
            "target": target, "summary": summary}
