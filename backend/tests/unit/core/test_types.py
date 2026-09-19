"""P1-01: types are frozen, JSON-safe and round-trip losslessly (02 §7, §9)."""

import dataclasses
import json

import pytest

from proofchain_core.types import (
    BBox,
    ChangeRegion,
    Chunk,
    IntegrityTree,
    LocalizationMethod,
    LocalizationResult,
    LocalizationStatus,
    Page,
    RegionType,
    Section,
)

H1 = "a" * 64
H2 = "b" * 64


def make_chunk(index: int = 0) -> Chunk:
    return Chunk(
        id=f"p0-c{index}",
        page=0,
        index=index,
        text="Payment is due in 30 days.",
        bbox=BBox(72.0, 100.5, 300.0, 120.25),
        leaf_hash=H1,
    )


def make_tree() -> IntegrityTree:
    chunk = make_chunk()
    return IntegrityTree(
        canon_version=1,
        file_hash=H1,
        text_root=H2,
        page_count=1,
        pages=(Page(index=0, root=H2, chunks=(chunk,)),),
        sections=(Section(id="S0", title="Preamble", chunk_ids=(chunk.id,), hash=H1),),
    )


def make_region() -> ChangeRegion:
    return ChangeRegion(
        id="R0",
        type=RegionType.MODIFIED,
        ref_chunk_id="p0-c0",
        cand_chunk_id="p0-c0",
        ref_page=0,
        cand_page=0,
        ref_text="Payment is due in 30 days.",
        cand_text="Payment is due in 90 days.",
        ref_bbox=BBox(1.0, 2.0, 3.0, 4.0),
        cand_bbox=BBox(1.0, 2.0, 3.0, 4.0),
        section_id="S0",
        section_title="Preamble",
    )


def make_result() -> LocalizationResult:
    return LocalizationResult(
        status=LocalizationStatus.CHANGED,
        regions=(make_region(),),
        changed_pages_ref=(0,),
        changed_pages_cand=(0,),
        method=LocalizationMethod.MERKLE_FAST_PATH,
        hash_comparisons=3,
        stats={"modified": 1, "inserted": 0, "deleted": 0},
    )


@pytest.mark.parametrize(
    "obj",
    [
        BBox(0.0, 1.0, 2.0, 3.0),
        make_chunk(),
        make_tree().pages[0],
        make_tree().sections[0],
        make_tree(),
        make_region(),
        make_result(),
    ],
    ids=lambda o: type(o).__name__,
)
def test_types_roundtrip(obj: object) -> None:
    cls = type(obj)
    as_dict = obj.to_dict()  # type: ignore[attr-defined]
    assert cls.from_dict(as_dict) == obj  # type: ignore[attr-defined]
    # Survives a real JSON round trip, not just dict copying.
    assert cls.from_dict(json.loads(json.dumps(as_dict))) == obj  # type: ignore[attr-defined]


@pytest.mark.parametrize("obj", [make_chunk(), make_tree(), make_region(), make_result()])
def test_types_frozen(obj: object) -> None:
    field = dataclasses.fields(obj)[0].name  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field, "x")


def test_to_dict_is_json_plain() -> None:
    d = make_result().to_dict()
    assert d["status"] == "CHANGED"
    assert d["method"] == "MERKLE_FAST_PATH"
    assert d["regions"][0]["type"] == "MODIFIED"
    assert d["regions"][0]["cand_bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert isinstance(d["changed_pages_ref"], list)
    json.dumps(d)  # no tuples-of-objects / enums leak through


def test_to_dict_key_order_stable() -> None:
    a = json.dumps(make_tree().to_dict(), sort_keys=True)
    b = json.dumps(make_tree().to_dict(), sort_keys=True)
    assert a == b
    assert list(make_tree().to_dict())[:3] == ["canon_version", "file_hash", "text_root"]


def test_optional_fields_default_none() -> None:
    region = ChangeRegion(id="R1", type=RegionType.INSERTED, cand_chunk_id="p1-c0", cand_page=1)
    assert region.ref_bbox is None
    round_tripped = ChangeRegion.from_dict(region.to_dict())
    assert round_tripped == region
    assert round_tripped.section_id is None


def test_tree_collections_are_tuples() -> None:
    tree = IntegrityTree.from_dict(make_tree().to_dict())
    assert isinstance(tree.pages, tuple)
    assert isinstance(tree.pages[0].chunks, tuple)
    assert isinstance(tree.sections[0].chunk_ids, tuple)
    hash(tree.pages[0].chunks[0])  # frozen + hashable
