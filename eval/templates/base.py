"""Template structures. A document type = header lines + numbered sections + closing lines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    heading: str
    clauses: tuple[str, ...]  # templates; the generator numbers them "<section>.<n> <text>"


@dataclass(frozen=True)
class TypeDef:
    name: str
    title: str
    header: tuple[tuple[str, str], ...]  # (block kind, template) before the numbered body
    sections: tuple[Section, ...]
    closing: tuple[tuple[str, str], ...]  # (block kind, template) after the body
    party_kind: str = "company"  # how party_a/party_b are drawn: "company" | "person"
