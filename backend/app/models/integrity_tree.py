"""integrity_trees collection (03_DATA_MODEL); `_id` is the revision id."""

from pydantic import Field

from app.models.base import MongoModel


class TreeChunk(MongoModel):
    id: str
    index: int
    text: str
    leaf_hash: str
    bbox: list[float]
    section_id: str | None = None


class TreePage(MongoModel):
    index: int
    root: str
    chunks: list[TreeChunk]


class TreeSection(MongoModel):
    id: str
    title: str
    chunk_ids: list[str]
    hash: str


class IntegrityTreeDoc(MongoModel):
    id: str = Field(alias="_id")  # revision id
    document_id: str
    canon_version: int
    file_hash: str
    text_root: str
    page_count: int
    pages: list[TreePage]
    sections: list[TreeSection] = Field(default_factory=list)
    page_levels: list[list[str]] | None = None  # derived by the P6 service, optional here
