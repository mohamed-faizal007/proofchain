"""Map a proofchain_core IntegrityTree to and from the stored integrity_trees document (03)."""

from app.models.integrity_tree import IntegrityTreeDoc, TreeChunk, TreePage, TreeSection
from proofchain_core.types import BBox, Chunk, IntegrityTree, Page, Section


def tree_to_doc(tree: IntegrityTree, revision_id: str, document_id: str) -> IntegrityTreeDoc:
    section_of = {cid: s.id for s in tree.sections for cid in s.chunk_ids}
    return IntegrityTreeDoc(
        _id=revision_id,
        document_id=document_id,
        canon_version=tree.canon_version,
        file_hash=tree.file_hash,
        text_root=tree.text_root,
        page_count=tree.page_count,
        pages=[
            TreePage(
                index=p.index,
                root=p.root,
                chunks=[
                    TreeChunk(
                        id=c.id,
                        index=c.index,
                        text=c.text,
                        leaf_hash=c.leaf_hash,
                        bbox=c.bbox.to_dict(),
                        section_id=section_of.get(c.id),
                    )
                    for c in p.chunks
                ],
            )
            for p in tree.pages
        ],
        sections=[
            TreeSection(id=s.id, title=s.title, chunk_ids=list(s.chunk_ids), hash=s.hash)
            for s in tree.sections
        ],
    )


def doc_to_tree(doc: IntegrityTreeDoc) -> IntegrityTree:
    """Inverse of `tree_to_doc`. Stored chunks carry no `page`; it is their page's index."""
    return IntegrityTree(
        canon_version=doc.canon_version,
        file_hash=doc.file_hash,
        text_root=doc.text_root,
        page_count=doc.page_count,
        pages=tuple(
            Page(
                index=p.index,
                root=p.root,
                chunks=tuple(
                    Chunk(
                        id=c.id,
                        page=p.index,
                        index=c.index,
                        text=c.text,
                        bbox=BBox.from_dict(c.bbox),
                        leaf_hash=c.leaf_hash,
                    )
                    for c in p.chunks
                ),
            )
            for p in doc.pages
        ),
        sections=tuple(
            Section(id=s.id, title=s.title, chunk_ids=tuple(s.chunk_ids), hash=s.hash)
            for s in doc.sections
        ),
    )
