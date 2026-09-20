"""Golden vector for the provenance event hash (ADR-019): literal expected output.

The serialized string and its SHA-256 below were computed independently with hashlib on a
hand-written string, never with the code under test. If this fails, every stored `event_hash`
would stop verifying: change the format only with a new ADR and a migration, then regenerate.
"""

import datetime as dt

import pytest

from app.models.provenance_event import ProvenanceEvent
from app.repositories.event_hash import canonical_event_json, compute_event_hash

PREV = "1f" * 32

GOLDEN_JSON = (
    '{"_id":"00000000-0000-4000-8000-000000000001",'
    '"actor_id":"00000000-0000-4000-8000-0000000000a1",'
    '"at":"2026-09-20T12:34:56.789Z",'
    '"data":{"comment":"Café – naïve \\"quoted\\"","flags":[true,null],'
    '"tx_hash":"0xabc","verdict":"OK","version_no":3},'
    '"document_id":"00000000-0000-4000-8000-0000000000d1",'
    f'"prev_event_hash":"{PREV}",'
    '"revision_id":"00000000-0000-4000-8000-0000000000f1",'
    '"type":"REVISION_APPROVED"}'
)
GOLDEN_HASH = "5da41e3a664679f5dbf1b281d1697d8ae113b851f477a7b3f2fc6798a68e83ba"


def _event(**over: object) -> ProvenanceEvent:
    fields: dict[str, object] = {
        "id": "00000000-0000-4000-8000-000000000001",
        "document_id": "00000000-0000-4000-8000-0000000000d1",
        "revision_id": "00000000-0000-4000-8000-0000000000f1",
        "type": "REVISION_APPROVED",
        "actor_id": "00000000-0000-4000-8000-0000000000a1",
        "at": dt.datetime(2026, 9, 20, 12, 34, 56, 789000, tzinfo=dt.UTC),
        "data": {
            "verdict": "OK",
            "version_no": 3,
            "tx_hash": "0xabc",
            "flags": [True, None],
            "comment": 'Café – naïve "quoted"',
        },
        "prev_event_hash": PREV,
        "event_hash": "0" * 64,
    }
    fields.update(over)
    return ProvenanceEvent.model_validate(fields)


def test_golden_canonical_json_literal() -> None:
    assert canonical_event_json(_event()) == GOLDEN_JSON


def test_golden_event_hash_literal() -> None:
    assert compute_event_hash(_event()) == GOLDEN_HASH


def test_event_hash_field_is_excluded_from_the_hash() -> None:
    assert compute_event_hash(_event(event_hash="f" * 64)) == GOLDEN_HASH


def test_data_key_order_does_not_matter() -> None:
    data = {"version_no": 3, "verdict": "OK"}
    reordered = {"verdict": "OK", "version_no": 3}
    assert compute_event_hash(_event(data=data)) == compute_event_hash(_event(data=reordered))


def test_genesis_event_serializes_null_prev() -> None:
    assert '"prev_event_hash":null' in canonical_event_json(_event(prev_event_hash=None))


def test_timestamp_is_utc_milliseconds_regardless_of_input_zone() -> None:
    plus2 = dt.timezone(dt.timedelta(hours=2))
    local = dt.datetime(2026, 9, 20, 14, 34, 56, 789000, tzinfo=plus2)
    assert compute_event_hash(_event(at=local)) == GOLDEN_HASH


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_event_json(_event(at=dt.datetime(2026, 9, 20, 12, 34, 56)))


@pytest.mark.parametrize(
    "bad",
    [{"x": 1.5}, {"x": float("nan")}, {"x": {"y": [1.0]}}, {"x": dt.datetime(2026, 1, 1)}],
)
def test_non_json_native_data_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        canonical_event_json(_event(data=bad))


def test_non_string_data_keys_rejected() -> None:
    ev = _event()
    ev.data = {1: "x"}  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        canonical_event_json(ev)
