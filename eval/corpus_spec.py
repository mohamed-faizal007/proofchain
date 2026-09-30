"""JSON spec of a base document: the exact ground truth that tamper operations edit (08 C.1).

A spec is a plain ``dict`` (JSON-native). Top level: ``spec_version, doc_id, index, doc_type, seed,
page_count_function, target_pages, page_count, title, blocks``. Each block:
``{id, kind: title|heading|clause|line|signature, text, entities: [{kind, value, start, end}]}``,
where ``text[start:end] == value``. Serialisation is byte-stable
(insertion order, no ASCII escaping).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SPEC_VERSION = 1


def dump_spec(spec: dict[str, Any]) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def load_spec(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: spec must be a JSON object")
    return data
