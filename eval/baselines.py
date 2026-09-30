"""Baselines the integrity tree is compared with (docs/08 C.3).

Each localizing baseline returns ``(ref_ids, cand_ids)``: the ids of the reference and candidate
chunks it flags as changed (id spaces kept apart, see metrics.py).

1. ``whole_file_changed``: SHA-256 of the file. Detects any byte change, including a harmless
   re-save, and cannot say where or what.
2. ``plain_diff``: a text diff of the chunk texts with no hashing. It localizes, but it needs the
   full reference text at verify time and offers no tamper evidence (nothing is anchored).
3. ``positional``: the comparison that the alignment step of docs/02 section 9.4 exists to avoid
   (ADR-006: "Positional comparison cascades after an insertion").
"""

from __future__ import annotations

from difflib import SequenceMatcher

from proofchain_core.types import Chunk


def whole_file_changed(ref_file_hash: str, cand_file_hash: str) -> bool:
    return ref_file_hash != cand_file_hash


def plain_diff(ref: list[Chunk], cand: list[Chunk]) -> tuple[set[str], set[str]]:
    """Diff of the chunk texts (difflib, no hashes, no Merkle tree): every chunk in a
    replace/delete/insert opcode is flagged."""
    matcher = SequenceMatcher(None, [c.text for c in ref], [c.text for c in cand], autojunk=False)
    ref_ids: set[str] = set()
    cand_ids: set[str] = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            ref_ids |= {c.id for c in ref[i1:i2]}
            cand_ids |= {c.id for c in cand[j1:j2]}
    return ref_ids, cand_ids


def positional(ref: list[Chunk], cand: list[Chunk]) -> tuple[set[str], set[str]]:
    """Positional chunk comparison WITHOUT alignment.

    Both trees are flattened in reading order (the same flattening ``localize`` aligns, 02 section
    9.4 step 4) and ``cand[i]`` is compared with ``ref[i]`` by index, by leaf hash. A pair whose
    hashes differ flags both chunks. Chunks past the end of the shorter sequence are flagged on
    their own side (deleted from the reference / inserted into the candidate). No sequence
    alignment is attempted, so one inserted or deleted chunk shifts every later index and every
    later chunk is flagged although it did not change: the insertion cascade that ADR-006 and
    02 section 9.4 ("a pure positional comparison would flag the rest of the document") describe.
    """
    ref_ids: set[str] = set()
    cand_ids: set[str] = set()
    for i in range(max(len(ref), len(cand))):
        if i >= len(cand):
            ref_ids.add(ref[i].id)
        elif i >= len(ref):
            cand_ids.add(cand[i].id)
        elif ref[i].leaf_hash != cand[i].leaf_hash:
            ref_ids.add(ref[i].id)
            cand_ids.add(cand[i].id)
    return ref_ids, cand_ids
