"""Small Markdown formatting helpers shared by the report modules."""

from __future__ import annotations

from typing import Any


def table(header: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def pct(x: float) -> str:
    return f"{x:.1%}"


def money(symbol: str, value: float) -> str:
    return f"{symbol}{value:,.0f}" if value == int(value) else f"{symbol}{value:,.2f}"


def fig(names: list[str]) -> str:
    return "\n".join(f"![{n}](figures/{n}.png)" for n in names)
