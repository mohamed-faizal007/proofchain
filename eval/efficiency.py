"""Merkle efficiency counts (docs/08 C.3, docs/02 section 12)."""

from __future__ import annotations

from typing import Any

from proofchain_core.hashing import page_node_hash
from proofchain_core.merkle import merkle_levels
from proofchain_core.types import IntegrityTree, LocalizationResult


def descent(ref_levels: list[list[str]], cand_levels: list[list[str]]) -> tuple[list[int], int]:
    """``changed_leaves_by_descent`` (core) plus a comparison counter: (leaf indices, compares).

    One comparison is one pair of node hashes looked at: the root pair, then both children of every
    mismatching node (O(k log n) for k changed leaves).
    """
    if [len(lv) for lv in ref_levels] != [len(lv) for lv in cand_levels]:
        raise ValueError("trees must have the same shape (leaf count)")
    top = len(ref_levels) - 1
    comparisons = len(ref_levels[top])
    frontier = [j for j in range(len(ref_levels[top])) if ref_levels[top][j] != cand_levels[top][j]]
    for lvl in range(top, 0, -1):
        below = len(ref_levels[lvl - 1])
        children = [c for j in frontier for c in (2 * j, 2 * j + 1) if c < below]
        comparisons += len(children)
        frontier = [c for c in children if ref_levels[lvl - 1][c] != cand_levels[lvl - 1][c]]
    return frontier, comparisons


def tree_descent(ref: IntegrityTree, cand: IntegrityTree) -> int | None:
    """Comparisons of a descent over the page-level tree, then over each changed page's chunk tree
    (a page whose chunk count changed is aligned: its leaves are all compared). None when the page
    counts differ (no page-level descent exists)."""
    if ref.page_count != cand.page_count:
        return None
    pages, total = descent(
        merkle_levels([p.root for p in ref.pages], node=page_node_hash),
        merkle_levels([p.root for p in cand.pages], node=page_node_hash),
    )
    for p in pages:
        a, b = ref.pages[p].chunks, cand.pages[p].chunks
        if len(a) == len(b) and a:
            total += descent(
                merkle_levels([c.leaf_hash for c in a]), merkle_levels([c.leaf_hash for c in b])
            )[1]
        else:
            total += len(a) + len(b)
    return total


def case_efficiency(
    ref: IntegrityTree, cand: IntegrityTree, result: LocalizationResult
) -> dict[str, Any]:
    ref_chunks = sum(len(p.chunks) for p in ref.pages)
    cand_chunks = sum(len(p.chunks) for p in cand.pages)
    return {
        "method": None if result.method is None else result.method.value,
        "page_count": ref.page_count,
        "ref_chunks": ref_chunks,
        "cand_chunks": cand_chunks,
        "naive": ref_chunks + cand_chunks,  # every leaf hash of both trees, as a full alignment
        "hash_comparisons": result.hash_comparisons,
        "descent": tree_descent(ref, cand),
    }
