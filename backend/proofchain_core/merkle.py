"""Merkle tree over chunk hashes. Normative spec: docs/02_ALGORITHMS.md §6."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from proofchain_core.hashing import node_hash, page_node_hash

Side = Literal["left", "right"]
NodeFn = Callable[[str, str], str]


@dataclass(frozen=True, slots=True)
class ProofStep:
    """One sibling on the path to the root; `side` is where the sibling sits."""

    sibling: str
    side: Side

    def to_dict(self) -> dict[str, Any]:
        return {"sibling": self.sibling, "side": self.side}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProofStep":
        side = d["side"]
        if side not in ("left", "right"):
            raise ValueError(f"invalid side: {side!r}")
        return cls(sibling=d["sibling"], side=side)


def merkle_levels(hashes: list[str], *, node: NodeFn = node_hash) -> list[list[str]]:
    """Levels bottom-up (level 0 = leaves, last = [root]) (§6).

    `node` combines two siblings: `node_hash` for chunk trees, `page_node_hash`
    for the page-level tree (§7, ADR-017).

    Adjacent nodes pair left to right; an odd last node is promoted unchanged
    (never duplicated, which would allow CVE-2012-2459 mutation).
    """
    if not hashes:
        raise ValueError("merkle tree needs at least one hash")
    levels = [list(hashes)]
    while len(levels[-1]) > 1:
        cur = levels[-1]
        nxt = [node(cur[i], cur[i + 1]) for i in range(0, len(cur) - 1, 2)]
        if len(cur) % 2:
            nxt.append(cur[-1])
        levels.append(nxt)
    return levels


def merkle_root(hashes: list[str], *, node: NodeFn = node_hash) -> str:
    """Root of the tree; a single element is its own root (§6)."""
    return merkle_levels(hashes, node=node)[-1][0]


def page_merkle_root(page_roots: list[str]) -> str:
    """text_root: Merkle root over page roots with the page-level prefix (§7, ADR-017)."""
    return merkle_root(page_roots, node=page_node_hash)


def merkle_proof(hashes: list[str], i: int, *, node: NodeFn = node_hash) -> list[ProofStep]:
    """Audit path for leaf `i`; promoted nodes contribute no step (§6)."""
    if not 0 <= i < len(hashes):
        raise IndexError(f"leaf index {i} out of range for {len(hashes)} leaves")
    proof: list[ProofStep] = []
    idx = i
    for level in merkle_levels(hashes, node=node)[:-1]:
        if idx % 2 == 0:
            if idx + 1 < len(level):
                proof.append(ProofStep(sibling=level[idx + 1], side="right"))
        else:
            proof.append(ProofStep(sibling=level[idx - 1], side="left"))
        idx //= 2
    return proof


def verify_proof(leaf: str, proof: list[ProofStep], root: str, *, node: NodeFn = node_hash) -> bool:
    """Recompute the root from `leaf` along `proof` and compare (§6)."""
    cur = leaf
    try:
        for step in proof:
            if step.side == "right":
                cur = node(cur, step.sibling)
            elif step.side == "left":
                cur = node(step.sibling, cur)
            else:
                return False
    except ValueError:
        return False
    return cur == root


def changed_leaves_by_descent(
    ref_levels: list[list[str]], cand_levels: list[list[str]]
) -> list[int]:
    """Sorted leaf indices that differ, found by descending mismatching nodes (§12).

    Both trees must have the same leaf count; equal subtree hashes are skipped,
    giving O(k log n) comparisons for k changed leaves.
    """
    if [len(lv) for lv in ref_levels] != [len(lv) for lv in cand_levels]:
        raise ValueError("trees must have the same shape (leaf count)")
    top = len(ref_levels) - 1
    frontier = [j for j in range(len(ref_levels[top])) if ref_levels[top][j] != cand_levels[top][j]]
    for lvl in range(top, 0, -1):
        below = len(ref_levels[lvl - 1])
        frontier = [
            c
            for j in frontier
            for c in (2 * j, 2 * j + 1)
            if c < below and ref_levels[lvl - 1][c] != cand_levels[lvl - 1][c]
        ]
    return frontier
