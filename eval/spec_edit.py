"""Edits on a corpus spec (docs/08 C.1 / C.2): span replacement and applying edit records.

An *edit* is a JSON-native dict, self-contained so a tampered spec can be rebuilt from its base:
``{op, category, kind: replace|insert|delete, block_id, before, after, entities, ...}``
(``kind`` is replace, insert or delete).
``replace`` carries the new block text and entities; ``insert`` also ``insert_after`` (an existing
block id) and ``after_block_id`` (the new id); ``delete`` only ``block_id`` and ``before``.
"""

from __future__ import annotations

import copy
from typing import Any

from render import Cursor, block_height


def replace_span(
    text: str, entities: list[dict[str, Any]], start: int, end: int, new: str
) -> tuple[str, list[dict[str, Any]]]:
    """Replace ``text[start:end]`` and keep the entity offsets exact.

    An entity equal to the span takes the new value; entities before are kept, entities after are
    shifted; an entity partly overlapping the span is dropped.
    """
    delta = len(new) - (end - start)
    out: list[dict[str, Any]] = []
    for e in entities:
        if e["end"] <= start:
            out.append(dict(e))
        elif e["start"] >= end:
            out.append({**e, "start": e["start"] + delta, "end": e["end"] + delta})
        elif e["start"] == start and e["end"] == end:
            out.append({**e, "value": new, "end": start + len(new)})
    return text[:start] + new + text[end:], out


def next_block_id(spec: dict[str, Any]) -> str:
    return f"b{max(int(b['id'][1:]) for b in spec['blocks']) + 1:04d}"


def measure_pages(spec: dict[str, Any]) -> int:
    cursor = Cursor()
    for b in spec["blocks"]:
        cursor = cursor.advance(block_height(b["kind"], b["text"]))
    return cursor.page


def apply_edits(spec: dict[str, Any], edits: list[dict[str, Any]]) -> dict[str, Any]:
    """A new spec with the edits applied in order (the input is not modified)."""
    out = copy.deepcopy(spec)
    blocks: list[dict[str, Any]] = out["blocks"]
    for edit in edits:
        pos = next(
            i for i, b in enumerate(blocks) if b["id"] == edit.get("insert_after", edit["block_id"])
        )
        if edit["kind"] == "replace":
            blocks[pos]["text"] = edit["after"]
            blocks[pos]["entities"] = copy.deepcopy(edit["entities"])
        elif edit["kind"] == "insert":
            blocks.insert(
                pos + 1,
                {
                    "id": edit["after_block_id"],
                    "kind": "clause",
                    "text": edit["after"],
                    "entities": copy.deepcopy(edit["entities"]),
                },
            )
        elif edit["kind"] == "delete":
            del blocks[pos]
        else:
            raise ValueError(f"unknown edit kind {edit['kind']!r}")
    out["page_count"] = measure_pages(out)
    return out
