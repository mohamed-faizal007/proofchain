"""Canonical JSON + SHA-256 for provenance events. Format is normative: ADR-019.

Pinned by tests/unit/app/test_event_hash.py; do not change without a new ADR and a migration.
"""

import datetime as dt
import hashlib
import json
from typing import Any

from app.models.provenance_event import ProvenanceEvent


def format_at(at: dt.datetime) -> str:
    """UTC, exactly millisecond precision: YYYY-MM-DDTHH:MM:SS.mmmZ (ADR-019)."""
    if at.tzinfo is None:
        raise ValueError("event timestamp must be timezone-aware")
    utc = at.astimezone(dt.UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"


def _check_json_native(value: Any, path: str = "data") -> None:
    # bool is an int subclass, so it is covered by int.
    if value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check_json_native(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: keys must be str, got {type(key).__name__}")
            _check_json_native(item, f"{path}.{key}")
        return
    raise ValueError(f"{path}: unsupported type {type(value).__name__} (floats are not allowed)")


def canonical_event_json(event: ProvenanceEvent) -> str:
    _check_json_native(event.data)
    obj: dict[str, Any] = {
        "_id": event.id,
        "actor_id": event.actor_id,
        "at": format_at(event.at),
        "data": event.data,
        "document_id": event.document_id,
        "prev_event_hash": event.prev_event_hash,
        "revision_id": event.revision_id,
        "type": event.type,
    }
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def compute_event_hash(event: ProvenanceEvent) -> str:
    return hashlib.sha256(canonical_event_json(event).encode("utf-8")).hexdigest()
