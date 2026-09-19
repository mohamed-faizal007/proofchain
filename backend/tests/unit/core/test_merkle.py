"""Tests for 02_ALGORITHMS.md §6 Merkle tree (root, levels, proofs, descent)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from proofchain_core.hashing import leaf_hash, node_hash
from proofchain_core.merkle import (
    ProofStep,
    changed_leaves_by_descent,
    merkle_levels,
    merkle_proof,
    merkle_root,
    verify_proof,
)


def leaves(n: int) -> list[str]:
    return [leaf_hash(f"chunk-{i}") for i in range(n)]


def hand_root(h: list[str]) -> str:
    """Hand-built expected roots (odd node promoted, never duplicated)."""
    n = len(h)
    a, b, c, d, e = (h + [""] * 5)[:5]
    if n == 1:
        return a
    if n == 2:
        return node_hash(a, b)
    if n == 3:
        return node_hash(node_hash(a, b), c)
    if n == 4:
        return node_hash(node_hash(a, b), node_hash(c, d))
    if n == 5:
        return node_hash(node_hash(node_hash(a, b), node_hash(c, d)), e)
    raise AssertionError(n)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_known_answer_roots(n: int) -> None:
    h = leaves(n)
    assert merkle_root(h) == hand_root(h)


def test_single_leaf_root_is_the_leaf() -> None:
    h = leaves(1)
    assert merkle_root(h) == h[0]
    assert merkle_levels(h) == [h]
    assert merkle_proof(h, 0) == []


def test_levels_shape_for_five_leaves() -> None:
    h = leaves(5)
    levels = merkle_levels(h)
    assert [len(lv) for lv in levels] == [5, 3, 2, 1]
    assert levels[0] == h
    assert levels[1][2] == h[4]  # promoted unchanged
    assert levels[2][1] == h[4]  # promoted again


def test_odd_node_is_promoted_not_duplicated() -> None:
    a, b, c = leaves(3)
    # CVE-2012-2459: [a,b,c] and [a,b,c,c] must not share a root.
    assert merkle_root([a, b, c]) != merkle_root([a, b, c, c])
    assert merkle_root([a, b, c]) != node_hash(node_hash(a, b), node_hash(c, c))


def test_empty_list_is_an_error() -> None:
    with pytest.raises(ValueError):
        merkle_root([])
    with pytest.raises(ValueError):
        merkle_levels([])


def test_order_matters() -> None:
    a, b, c = leaves(3)
    assert merkle_root([a, b, c]) != merkle_root([b, a, c])


def test_proof_index_out_of_range() -> None:
    h = leaves(3)
    for bad in (-1, 3):
        with pytest.raises(IndexError):
            merkle_proof(h, bad)


def test_proof_steps_for_three_leaves() -> None:
    a, b, c = leaves(3)
    assert merkle_proof([a, b, c], 0) == [
        ProofStep(sibling=b, side="right"),
        ProofStep(sibling=c, side="right"),
    ]
    assert merkle_proof([a, b, c], 1) == [
        ProofStep(sibling=a, side="left"),
        ProofStep(sibling=c, side="right"),
    ]
    # c is promoted at level 0, so it contributes no step there.
    assert merkle_proof([a, b, c], 2) == [ProofStep(sibling=node_hash(a, b), side="left")]


def test_proof_step_dict_round_trip() -> None:
    step = ProofStep(sibling=leaf_hash("x"), side="left")
    assert ProofStep.from_dict(step.to_dict()) == step
    assert list(step.to_dict()) == ["sibling", "side"]


@pytest.mark.parametrize("n", range(1, 34))
def test_every_leaf_proof_verifies_for_n_1_to_33(n: int) -> None:
    h = leaves(n)
    root = merkle_root(h)
    assert merkle_levels(h)[-1] == [root]
    for i in range(n):
        assert verify_proof(h[i], merkle_proof(h, i), root)


@pytest.mark.parametrize("n", [2, 3, 5, 8, 13, 33])
def test_tampered_proofs_fail(n: int) -> None:
    h = leaves(n)
    root = merkle_root(h)
    for i in range(n):
        proof = merkle_proof(h, i)
        assert not verify_proof(leaf_hash("forged"), proof, root)
        assert not verify_proof(h[i], proof, leaf_hash("wrong-root"))
        other = (i + 1) % n
        assert not verify_proof(h[other], proof, root)
        if proof:
            flipped = ProofStep(
                sibling=proof[0].sibling,
                side="left" if proof[0].side == "right" else "right",
            )
            assert not verify_proof(h[i], [flipped, *proof[1:]], root)
            assert not verify_proof(h[i], proof[:-1], root)


@given(st.lists(st.text(max_size=20), min_size=1, max_size=40))
def test_property_proofs_and_determinism(texts: list[str]) -> None:
    h = [leaf_hash(t) for t in texts]
    root = merkle_root(h)
    assert merkle_root(list(h)) == root
    assert merkle_levels(h) == merkle_levels(list(h))
    for i in range(len(h)):
        assert verify_proof(h[i], merkle_proof(h, i), root)


@given(st.lists(st.text(max_size=10), min_size=2, max_size=40, unique=True), st.data())
def test_property_changing_any_leaf_changes_root(texts: list[str], data: st.DataObject) -> None:
    h = [leaf_hash(t) for t in texts]
    i = data.draw(st.integers(0, len(h) - 1))
    h2 = list(h)
    h2[i] = leaf_hash("\x00changed\x00")
    assert merkle_root(h2) != merkle_root(h)


def naive_changed(a: list[str], b: list[str]) -> list[int]:
    return [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]


def test_descent_identical_returns_empty() -> None:
    levels = merkle_levels(leaves(7))
    assert changed_leaves_by_descent(levels, merkle_levels(leaves(7))) == []


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 9])
def test_descent_single_change_each_position(n: int) -> None:
    ref = leaves(n)
    for i in range(n):
        cand = list(ref)
        cand[i] = leaf_hash("edited")
        got = changed_leaves_by_descent(merkle_levels(ref), merkle_levels(cand))
        assert got == [i]


@given(
    st.integers(1, 40),
    st.sets(st.integers(0, 39), max_size=10),
)
def test_property_descent_matches_naive(n: int, positions: set[int]) -> None:
    ref = leaves(n)
    cand = list(ref)
    for p in positions:
        if p < n:
            cand[p] = leaf_hash(f"edit-{p}")
    got = changed_leaves_by_descent(merkle_levels(ref), merkle_levels(cand))
    assert got == naive_changed(ref, cand)
    assert got == sorted(got)


def test_descent_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        changed_leaves_by_descent(merkle_levels(leaves(3)), merkle_levels(leaves(4)))
