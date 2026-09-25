"""Map a proofchain_core IntegrityTree to the stored integrity_trees document (03_DATA_MODEL)."""

from app.models.integrity_tree import IntegrityTreeDoc, TreeChunk, TreePage, TreeSection
from proofchain_core.types import IntegrityTree


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
