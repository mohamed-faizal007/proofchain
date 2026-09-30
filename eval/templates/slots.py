"""Slot filling for clause templates. Everything here is locale- and clock-independent.

A template is a ``str.format``-style string, e.g. ``"{party_a} shall pay {amount} by {date}."``.
Each field is filled from ``SlotContext``; fields that carry an editable value (amount, date,
percentage, number, party) are recorded as entities with exact character offsets.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from string import Formatter
from typing import Any

from faker import Faker

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_DATE_START = date(2020, 1, 1)
_DATE_SPAN_DAYS = 2200

ITEMS = (
    "consulting services",
    "software licence",
    "maintenance visit",
    "printed materials",
    "cloud hosting",
    "training session",
    "site survey",
    "equipment rental",
    "audit support",
    "logistics handling",
)

# field name -> entity kind (None: filled but not an editable entity)
FIELD_KINDS: dict[str, str | None] = {
    "party_a": "PARTY",
    "party_b": "PARTY",
    "person": "PARTY",
    "amount": "AMOUNT",
    "date": "DATE",
    "pct": "PERCENTAGE",
    "days": "NUMBER",
    "months": "NUMBER",
    "num": "NUMBER",
    "city": None,
    "item": None,
    "address": None,
    "ref": None,
}


def format_inr(n: int) -> str:
    """Indian digit grouping with the rupee sign: 4500000 -> ₹45,00,000."""
    s = str(n)
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join([*groups, tail])


def format_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


@dataclass
class SlotContext:
    rng: random.Random
    fake: Faker
    fixed: dict[str, str] = field(default_factory=dict)

    def value(self, name: str) -> str:
        if name in self.fixed:
            return self.fixed[name]
        rng = self.rng
        if name == "amount":
            return format_inr(rng.randint(5, 999) * 10 ** rng.choice((2, 3, 4, 5)))
        if name == "date":
            return format_date(_DATE_START + timedelta(days=rng.randint(0, _DATE_SPAN_DAYS)))
        if name == "pct":
            return f"{rng.choice((2, 5, 7.5, 10, 12, 15, 18, 20, 25))}%".replace(".0", "")
        if name == "days":
            return str(rng.choice((7, 10, 15, 30, 45, 60, 90)))
        if name == "months":
            return str(rng.choice((3, 6, 9, 11, 12, 24, 36)))
        if name == "num":
            return str(rng.randint(2, 40))
        if name == "city":
            return str(self.fake.city())
        if name == "item":
            return rng.choice(ITEMS)
        if name == "address":
            return str(self.fake.street_address()).replace("\n", ", ")
        if name == "ref":
            return f"REF-{rng.randint(1000, 9999)}"
        raise KeyError(f"unknown template field {name!r}")


def fill(template: str, ctx: SlotContext) -> tuple[str, list[dict[str, Any]]]:
    """Render a template; return the text and its entities in reading order."""
    out: list[str] = []
    entities: list[dict[str, Any]] = []
    pos = 0
    for literal, name, _spec, _conv in Formatter().parse(template):
        out.append(literal)
        pos += len(literal)
        if name is None:
            continue
        val = ctx.value(name)
        kind = FIELD_KINDS[name]
        if kind is not None:
            entities.append({"kind": kind, "value": val, "start": pos, "end": pos + len(val)})
        out.append(val)
        pos += len(val)
    return "".join(out), entities
