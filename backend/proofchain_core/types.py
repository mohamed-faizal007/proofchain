"""Frozen data types for the integrity tree and localization (02 §4, §7, §9).

Pure data: no hashing or canonicalization logic lives here. Hashes are lowercase
hex strings. Every type serializes to plain JSON-safe dicts with a stable key
order (field declaration order) and rebuilds losslessly via ``from_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RegionType(StrEnum):
    MODIFIED = "MODIFIED"
    INSERTED = "INSERTED"
    DELETED = "DELETED"


class LocalizationStatus(StrEnum):
    IDENTICAL = "IDENTICAL"
    CONTENT_EQUIVALENT = "CONTENT_EQUIVALENT"
    CHANGED = "CHANGED"


class LocalizationMethod(StrEnum):
    MERKLE_FAST_PATH = "MERKLE_FAST_PATH"
    ALIGNMENT = "ALIGNMENT"


@dataclass(frozen=True)
class BBox:
    """Block bounding box in PDF points, top-left origin: x0, y0, x1, y1."""

    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    @classmethod
    def from_dict(cls, data: list[float]) -> BBox:
        x0, y0, x1, y1 = data
        return cls(float(x0), float(y0), float(x1), float(y1))


def _bbox_out(bbox: BBox | None) -> list[float] | None:
    return None if bbox is None else bbox.to_dict()


def _bbox_in(data: list[float] | None) -> BBox | None:
    return None if data is None else BBox.from_dict(data)


@dataclass(frozen=True)
class Chunk:
    id: str
    page: int
    index: int
    text: str
    bbox: BBox
    leaf_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page": self.page,
            "index": self.index,
            "text": self.text,
            "bbox": self.bbox.to_dict(),
            "leaf_hash": self.leaf_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        return cls(
            id=data["id"],
            page=data["page"],
            index=data["index"],
            text=data["text"],
            bbox=BBox.from_dict(data["bbox"]),
            leaf_hash=data["leaf_hash"],
        )


@dataclass(frozen=True)
class Page:
    index: int
    root: str
    chunks: tuple[Chunk, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "root": self.root,
            "chunks": [c.to_dict() for c in self.chunks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Page:
        return cls(
            index=data["index"],
            root=data["root"],
            chunks=tuple(Chunk.from_dict(c) for c in data["chunks"]),
        )


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    chunk_ids: tuple[str, ...]
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "chunk_ids": list(self.chunk_ids),
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Section:
        return cls(
            id=data["id"],
            title=data["title"],
            chunk_ids=tuple(data["chunk_ids"]),
            hash=data["hash"],
        )


@dataclass(frozen=True)
class IntegrityTree:
    canon_version: int
    file_hash: str
    text_root: str
    page_count: int
    pages: tuple[Page, ...]
    sections: tuple[Section, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "canon_version": self.canon_version,
            "file_hash": self.file_hash,
            "text_root": self.text_root,
            "page_count": self.page_count,
            "pages": [p.to_dict() for p in self.pages],
            "sections": [s.to_dict() for s in self.sections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntegrityTree:
        return cls(
            canon_version=data["canon_version"],
            file_hash=data["file_hash"],
            text_root=data["text_root"],
            page_count=data["page_count"],
            pages=tuple(Page.from_dict(p) for p in data["pages"]),
            sections=tuple(Section.from_dict(s) for s in data["sections"]),
        )


@dataclass(frozen=True)
class ChangeRegion:
    id: str
    type: RegionType
    ref_chunk_id: str | None = None
    cand_chunk_id: str | None = None
    ref_page: int | None = None
    cand_page: int | None = None
    ref_text: str | None = None
    cand_text: str | None = None
    cand_bbox: BBox | None = None
    ref_bbox: BBox | None = None
    section_id: str | None = None
    section_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "ref_chunk_id": self.ref_chunk_id,
            "cand_chunk_id": self.cand_chunk_id,
            "ref_page": self.ref_page,
            "cand_page": self.cand_page,
            "ref_text": self.ref_text,
            "cand_text": self.cand_text,
            "cand_bbox": _bbox_out(self.cand_bbox),
            "ref_bbox": _bbox_out(self.ref_bbox),
            "section_id": self.section_id,
            "section_title": self.section_title,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChangeRegion:
        return cls(
            id=data["id"],
            type=RegionType(data["type"]),
            ref_chunk_id=data.get("ref_chunk_id"),
            cand_chunk_id=data.get("cand_chunk_id"),
            ref_page=data.get("ref_page"),
            cand_page=data.get("cand_page"),
            ref_text=data.get("ref_text"),
            cand_text=data.get("cand_text"),
            cand_bbox=_bbox_in(data.get("cand_bbox")),
            ref_bbox=_bbox_in(data.get("ref_bbox")),
            section_id=data.get("section_id"),
            section_title=data.get("section_title"),
        )


@dataclass(frozen=True)
class LocalizationResult:
    status: LocalizationStatus
    regions: tuple[ChangeRegion, ...]
    changed_pages_ref: tuple[int, ...]
    changed_pages_cand: tuple[int, ...]
    method: LocalizationMethod | None
    hash_comparisons: int
    stats: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "regions": [r.to_dict() for r in self.regions],
            "changed_pages_ref": list(self.changed_pages_ref),
            "changed_pages_cand": list(self.changed_pages_cand),
            "method": None if self.method is None else self.method.value,
            "hash_comparisons": self.hash_comparisons,
            "stats": dict(self.stats),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LocalizationResult:
        method = data["method"]
        return cls(
            status=LocalizationStatus(data["status"]),
            regions=tuple(ChangeRegion.from_dict(r) for r in data["regions"]),
            changed_pages_ref=tuple(data["changed_pages_ref"]),
            changed_pages_cand=tuple(data["changed_pages_cand"]),
            method=None if method is None else LocalizationMethod(method),
            hash_comparisons=data["hash_comparisons"],
            stats=dict(data["stats"]),
        )
