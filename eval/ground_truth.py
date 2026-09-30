"""Ground truth of one tamper case from the two rendered PDFs (docs/08 C.2).

Deliberately does NOT call ``proofchain_core.localize``: the changed chunks are found with
``difflib`` over the two chunk-hash sequences, so P9-03 can score localize() against a diff that
shares only extraction and chunking with it. tests/test_tamper.py cross-checks this result against
a plain string diff of the two specs, which shares nothing with core.
"""

from __future__ import annotations

import difflib
from typing import Any

from proofchain_core.types import Chunk, IntegrityTree

_TYPES = {"replace": "MODIFIED", "insert": "INSERTED", "delete": "DELETED"}


def chunks_of(tree: IntegrityTree) -> list[Chunk]:
    return [c for p in tree.pages for c in p.chunks]


def tree_summary(tree: IntegrityTree) -> dict[str, Any]:
    return {
        "file_hash": tree.file_hash,
        "text_root": tree.text_root,
        "page_count": tree.page_count,
        "chunk_count": len(chunks_of(tree)),
    }


def derive_truth(ref: IntegrityTree, cand: IntegrityTree) -> dict[str, Any]:
    a, b = chunks_of(ref), chunks_of(cand)
    matcher = difflib.SequenceMatcher(
        None, [c.leaf_hash for c in a], [c.leaf_hash for c in b], autojunk=False
    )
    regions: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        regions.append(
            {
                "type": _TYPES[tag],
                "ref_chunk_ids": [c.id for c in a[i1:i2]],
                "cand_chunk_ids": [c.id for c in b[j1:j2]],
                "ref_texts": [c.text for c in a[i1:i2]],
                "cand_texts": [c.text for c in b[j1:j2]],
            }
        )
    ref_ids = [i for r in regions for i in r["ref_chunk_ids"]]
    cand_ids = [i for r in regions for i in r["cand_chunk_ids"]]

    def pages(ids: list[str]) -> list[int]:
        return sorted({int(i[1 : i.index("-")]) for i in ids})

    return {
        "file_hash_changed": ref.file_hash != cand.file_hash,
        "text_root_changed": ref.text_root != cand.text_root,
        "changed_ref_chunk_ids": ref_ids,
        "changed_cand_chunk_ids": cand_ids,
        "changed_pages_ref": pages(ref_ids),
        "changed_pages_cand": pages(cand_ids),
        "regions": regions,
    }
