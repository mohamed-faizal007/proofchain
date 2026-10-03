"""Figures for the evaluation report (docs/08 C.3): PNG and PDF, byte-identical for identical input.

Palette: the validated categorical order blue, orange, aqua (dataviz skill, light surface). Aqua
is below 3:1 against the surface, so every series is also direct-labelled or sits in a table in
REPORT.md. One measure per axis; two measures of different scale go in two panels.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
PNG_META = {"Software": None}
PDF_META = {"Creator": None, "Producer": None, "CreationDate": None}

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "pdf.fonttype": 42,
        "font.size": 9,
        "svg.hashsalt": "proofchain",
    }
)


def _save(fig: Figure, directory: Path, name: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"{name}.png", directory / f"{name}.pdf"]
    fig.savefig(paths[0], dpi=150, metadata=PNG_META)
    fig.savefig(paths[1], metadata=PDF_META)
    plt.close(fig)
    return paths


def _label_end(
    ax: Axes, xs: list[float], ys: list[float], text: str, color: str, dy: float = 0
) -> None:
    ax.annotate(
        text, (xs[-1], ys[-1]), xytext=(5, dy), textcoords="offset points", va="center", color=INK
    )
    ax.plot(
        xs[-1:],
        ys[-1:],
        "o",
        color=color,
        markersize=5,
        markeredgecolor=SURFACE,
        markeredgewidth=1.5,
    )


def efficiency(by_page: dict[str, dict[str, Any]], directory: Path) -> list[Path]:
    keys = sorted(by_page, key=int)
    xs = [float(int(k)) for k in keys]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for field, color, label, dy in (
        ("mean_naive", ORANGE, "naive chunk scan", 0),
        ("mean_hash_comparisons", BLUE, "Merkle (all comparisons)", 9),
        ("mean_descent", AQUA, "Merkle descent only", -9),
    ):
        ys = [float(by_page[k][field]) for k in keys]
        ax.plot(xs, ys, color=color, linewidth=2, label=label)
        _label_end(ax, xs, ys, label, color, dy)
    ax.set_xlabel("document pages")
    ax.set_ylabel("mean hash comparisons per case")
    ax.set_title("Merkle localization effort vs page count", loc="left")
    ax.set_xlim(right=max(xs) * 1.45)
    fig.tight_layout()
    return _save(fig, directory, "efficiency")


def latency(rows: list[dict[str, str]], directory: Path) -> list[Path]:
    xs = [float(r["page_count"]) for r in rows]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for field, color, label, dy in (
        ("build_tree_ms", BLUE, "build tree", -9),
        ("verify_ms", ORANGE, "verify (build + localize)", 9),
        ("localize_ms", AQUA, "localize", 0),
    ):
        ys = [float(r[field]) for r in rows]
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=5, label=label)
        _label_end(ax, xs, ys, label, color, dy)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("document pages (log)")
    ax.set_ylabel("median time, ms (log)")
    ax.set_title("Latency vs page count (one machine, median of runs)", loc="left")
    ax.set_xlim(right=max(xs) * 4)
    fig.tight_layout()
    return _save(fig, directory, "latency")


def localization(chunk: dict[str, dict[str, Any]], directory: Path) -> list[Path]:
    methods = [
        ("localize", "ProofChain"),
        ("positional", "positional"),
        ("plain_diff", "plain diff*"),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    width = 0.36
    for offset, field, color in ((-width / 2, "precision", BLUE), (width / 2, "recall", ORANGE)):
        vals = [float(chunk[m][field]) for m, _ in methods]
        bars = ax.bar([i + offset for i in range(3)], vals, width - 0.04, color=color, label=field)
        for bar, v in zip(bars, vals, strict=True):
            ax.annotate(
                f"{v:.2f}",
                (bar.get_x() + bar.get_width() / 2, v),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                color=INK,
            )
    ax.set_xticks(range(3), [label for _, label in methods])
    ax.set_ylim(0, 1.3)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_ylabel("chunk level")
    ax.legend(frameon=False, ncols=2, loc="upper center")
    ax.set_title("Localization: precision and recall", loc="left")
    fig.text(
        0.01,
        0.01,
        "* plain diff is handed the trusted reference text; it has no tamper evidence.",
        color=MUTED,
        fontsize=7,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return _save(fig, directory, "localization")


def classification(rows: list[dict[str, str]], directory: Path) -> list[Path]:
    arms = [("rules", BLUE), ("rules_ner", ORANGE), ("rules_ner_emb", AQUA)]
    cats = [r["category"] for r in rows if r["arm"] == "rules"]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    height = 0.26
    for j, (arm, color) in enumerate(arms):
        f1 = {r["category"]: float(r["f1"]) for r in rows if r["arm"] == arm}
        ax.barh(
            [i + (j - 1) * height for i in range(len(cats))],
            [f1[c] for c in cats],
            height - 0.03,
            color=color,
            label=arm,
        )
    ax.set_yticks(range(len(cats)), cats)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("F1")
    ax.legend(frameon=False, loc="lower left", fontsize=8)
    ax.set_title("Per-category F1 by classifier arm", loc="left")
    fig.tight_layout()
    return _save(fig, directory, "classification")


def _median(vals: list[float]) -> float:
    ordered = sorted(vals)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def chain(data: dict[str, Any], directory: Path) -> list[Path]:
    """Left: median gas per version kind (bars: the samples differ by about 12 gas, so a dot
    plot would be one line). Right: every anchoring latency sample with its median."""
    samples = data["samples"]
    kinds = [(k, c, lab) for k, c, lab in (("v1", BLUE, "first"), ("subsequent", ORANGE, "later"))]
    by_kind = {k: [s for s in samples if s["kind"] == k] for k, _, _ in kinds}
    kinds = [x for x in kinds if by_kind[x[0]]]
    fig, (ax_gas, ax_lat) = plt.subplots(1, 2, figsize=(6.8, 3.6))
    ticks = [f"{lab} version\n(n={len(by_kind[k])})" for k, _, lab in kinds]

    gas = [_median([s["gas_used"] for s in by_kind[k]]) for k, _, _ in kinds]
    bars = ax_gas.bar(range(len(kinds)), gas, 0.55, color=[c for _, c, _ in kinds])
    for bar, g in zip(bars, gas, strict=True):
        ax_gas.annotate(
            f"{g:,.0f}",
            (bar.get_x() + bar.get_width() / 2, g),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            color=INK,
        )
    ax_gas.set_ylim(0, max(gas) * 1.15)
    ax_gas.set_ylabel("median gas used")
    ax_gas.set_title("Gas per anchorVersion", loc="left", fontsize=9, pad=10)

    for i, (k, color, _) in enumerate(kinds):
        vals = [s["latency_s"] for s in by_kind[k]]
        spread = [i + (j - (len(vals) - 1) / 2) * 0.05 for j in range(len(vals))]
        ax_lat.plot(spread, vals, "o", color=color, markersize=6, markeredgecolor=SURFACE)
        med = _median(vals)
        ax_lat.hlines(med, i - 0.3, i + 0.3, color=INK, linewidth=1.5)
        ax_lat.annotate(
            f"median {med:.1f} s",
            (i + 0.3, med),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            color=INK,
            fontsize=7,
        )
    ax_lat.set_ylim(bottom=0)
    ax_lat.set_xlim(-0.6, len(kinds) - 0.1)
    ax_lat.set_ylabel("seconds")
    title = f"Anchoring latency ({data['target']}, {data.get('confirmations', '?')} conf.)"
    ax_lat.set_title(title, loc="left", fontsize=9, pad=10)

    for ax in (ax_gas, ax_lat):
        ax.set_xticks(range(len(kinds)), ticks)
    fig.tight_layout()
    return _save(fig, directory, "chain")
