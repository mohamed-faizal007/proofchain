"""Compare two integrity trees to localize changes (02 §9)."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from proofchain_core.types import (
    ChangeRegion,
    Chunk,
    IntegrityTree,
    LocalizationMethod,
    LocalizationResult,
    LocalizationStatus,
    RegionType,
)

PAIR_THRESHOLD = 0.30  # §9.4: minimum text ratio for a replace pair to be MODIFIED


@dataclass(frozen=True)
class _Pair:
    type: RegionType
    ref: Chunk | None
    cand: Chunk | None


def _pair_replace(ref: list[Chunk], cand: list[Chunk]) -> list[_Pair]:
    """Pair the chunks of a `replace` opcode greedily by text ratio (§9.4)."""
    scores = {
        (i, j): SequenceMatcher(None, a.text, b.text).ratio()
        for i, a in enumerate(ref)
        for j, b in enumerate(cand)
    }
    ref_left = list(range(len(ref)))
    cand_left = list(range(len(cand)))
    matched: list[tuple[int, int]] = []
    while ref_left and cand_left:
        best: tuple[float, int, int] | None = None
        for i in ref_left:  # ascending scan + strict '>' keeps the lower index on ties
            for j in cand_left:
                if best is None or scores[(i, j)] > best[0]:
                    best = (scores[(i, j)], i, j)
        assert best is not None
        if best[0] < PAIR_THRESHOLD:
            break
        matched.append((best[1], best[2]))
        ref_left.remove(best[1])
        cand_left.remove(best[2])
    pairs = [_Pair(RegionType.MODIFIED, ref[i], cand[j]) for i, j in sorted(matched)]
    pairs += [_Pair(RegionType.DELETED, ref[i], None) for i in ref_left]
    pairs += [_Pair(RegionType.INSERTED, None, cand[j]) for j in cand_left]
    return pairs


def _align(ref: list[Chunk], cand: list[Chunk]) -> list[_Pair]:
    """Diff two chunk sequences by leaf hash (§9.4)."""
    matcher = SequenceMatcher(
        None, [c.leaf_hash for c in ref], [c.leaf_hash for c in cand], autojunk=False
    )
    pairs: list[_Pair] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            pairs += [_Pair(RegionType.DELETED, c, None) for c in ref[i1:i2]]
        elif tag == "insert":
            pairs += [_Pair(RegionType.INSERTED, None, c) for c in cand[j1:j2]]
        elif tag == "replace":
            pairs += _pair_replace(ref[i1:i2], cand[j1:j2])
    return pairs


def _flatten(tree: IntegrityTree) -> list[Chunk]:
    return [c for page in tree.pages for c in page.chunks]


def _fast_path_pages(ref: IntegrityTree, cand: IntegrityTree) -> list[int] | None:
    """Mismatched page positions, or None when the fast path does not apply (§9.3).

    Spill-over: a mismatched page whose chunk count changed and that has a
    mismatched neighbour may have exchanged content with it, so the whole
    document is aligned instead.
    """
    if ref.page_count != cand.page_count:
        return None
    mismatched = [p for p in range(ref.page_count) if ref.pages[p].root != cand.pages[p].root]
    changed = set(mismatched)
    for p in mismatched:
        if len(ref.pages[p].chunks) != len(cand.pages[p].chunks) and (
            p - 1 in changed or p + 1 in changed
        ):
            return None
    return mismatched


def _section_index(tree: IntegrityTree) -> dict[str, tuple[str, str]]:
    return {cid: (s.id, s.title) for s in tree.sections for cid in s.chunk_ids}


def _region(
    n: int,
    pair: _Pair,
    ref_sections: dict[str, tuple[str, str]],
    cand_sections: dict[str, tuple[str, str]],
) -> ChangeRegion:
    ref, cand = pair.ref, pair.cand
    section = (
        cand_sections.get(cand.id)
        if cand is not None
        else ref_sections.get(ref.id)
        if ref is not None
        else None
    )
    return ChangeRegion(
        id=f"r{n}",
        type=pair.type,
        ref_chunk_id=None if ref is None else ref.id,
        cand_chunk_id=None if cand is None else cand.id,
        ref_page=None if ref is None else ref.page,
        cand_page=None if cand is None else cand.page,
        ref_text=None if ref is None else ref.text,
        cand_text=None if cand is None else cand.text,
        cand_bbox=None if cand is None else cand.bbox,
        ref_bbox=None if ref is None else ref.bbox,
        section_id=None if section is None else section[0],
        section_title=None if section is None else section[1],
    )


def _empty(status: LocalizationStatus) -> LocalizationResult:
    return LocalizationResult(
        status=status,
        regions=(),
        changed_pages_ref=(),
        changed_pages_cand=(),
        method=None,
        hash_comparisons=0,
        stats={"modified": 0, "inserted": 0, "deleted": 0},
    )


def localize(ref: IntegrityTree, cand: IntegrityTree) -> LocalizationResult:
    """Localize the changes from `ref` to `cand` (§9).

    `hash_comparisons` counts page-root comparisons (fast path attempted) plus
    the leaf hashes fed to the alignment of the scope actually diffed.
    """
    if ref.file_hash == cand.file_hash:
        return _empty(LocalizationStatus.IDENTICAL)
    if ref.text_root == cand.text_root:
        return _empty(LocalizationStatus.CONTENT_EQUIVALENT)

    pages = _fast_path_pages(ref, cand)
    pairs: list[_Pair] = []
    if pages is not None:
        method = LocalizationMethod.MERKLE_FAST_PATH
        comparisons = ref.page_count
        for p in pages:
            a, b = list(ref.pages[p].chunks), list(cand.pages[p].chunks)
            comparisons += len(a) + len(b)
            pairs += _align(a, b)
    else:
        method = LocalizationMethod.ALIGNMENT
        a, b = _flatten(ref), _flatten(cand)
        comparisons = (ref.page_count if ref.page_count == cand.page_count else 0) + len(a) + len(b)
        pairs = _align(a, b)

    ref_sections, cand_sections = _section_index(ref), _section_index(cand)
    regions = tuple(
        _region(n, pair, ref_sections, cand_sections) for n, pair in enumerate(pairs, start=1)
    )
    return LocalizationResult(
        status=LocalizationStatus.CHANGED,
        regions=regions,
        changed_pages_ref=tuple(sorted({r.ref_page for r in regions if r.ref_page is not None})),
        changed_pages_cand=tuple(sorted({r.cand_page for r in regions if r.cand_page is not None})),
        method=method,
        hash_comparisons=comparisons,
        stats={
            "modified": sum(r.type is RegionType.MODIFIED for r in regions),
            "inserted": sum(r.type is RegionType.INSERTED for r in regions),
            "deleted": sum(r.type is RegionType.DELETED for r in regions),
        },
    )
