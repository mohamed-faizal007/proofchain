"""tree_to_doc / doc_to_tree: the stored integrity tree maps back to the exact core tree (P5-06)."""

from app.models.integrity_tree import IntegrityTreeDoc
from app.services.tree_mapping import doc_to_tree, tree_to_doc
from proofchain_core import build_integrity_tree
from tests.unit.app.docs_env import PDFS


def test_doc_to_tree_round_trips_contract_3page() -> None:
    tree = build_integrity_tree((PDFS / "contract_3page.pdf").read_bytes())
    assert tree.page_count == 3 and tree.sections  # multi-page, with sections: not a trivial tree

    doc = tree_to_doc(tree, "rev-1", "doc-1")

    assert doc_to_tree(doc) == tree


def test_doc_to_tree_round_trips_through_the_stored_form() -> None:
    """Same, after the Mongo shape (by-alias dump, then validate) that TreeRepository stores."""
    tree = build_integrity_tree((PDFS / "contract_3page.pdf").read_bytes())
    stored = tree_to_doc(tree, "rev-1", "doc-1").model_dump(by_alias=True)

    restored = doc_to_tree(IntegrityTreeDoc.model_validate(stored))

    assert restored == tree
    assert [c.page for p in restored.pages for c in p.chunks] == [
        p.index for p in tree.pages for _ in p.chunks
    ]
