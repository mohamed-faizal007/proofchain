"""Generate the base corpus: ``data/corpus/{doc_id}.pdf`` + ``{doc_id}.json`` (docs/08 C.1).

Usage (from eval/):  python generate_corpus.py --config configs/default.yaml [--seed N]
                     [--n-docs N] [--out DIR] [--index I ...]

Every document is a pure function of (config, global seed, document index): it gets its own
``random.Random`` and Faker instance seeded from ``doc_seed(seed, index)``. No state is shared
between documents, so order, batching or parallel generation cannot change any output.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from pathlib import Path
from typing import Any

import yaml
from faker import Faker

from corpus_spec import SPEC_VERSION, dump_spec
from page_counts import PAGE_COUNT_FUNCTIONS
from render import Cursor, block_height, render_pdf
from templates import TYPES
from templates.base import TypeDef
from templates.slots import SlotContext, fill

EVAL_DIR = Path(__file__).resolve().parent


def load_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError(f"{path}: config must be a mapping")
    return cfg


def doc_seed(global_seed: int, index: int) -> int:
    """Deterministic 64-bit seed of one document (no shared generator, no Python hash())."""
    digest = hashlib.sha256(f"proofchain-corpus:{global_seed}:{index}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _draw_parties(tdef: TypeDef, fake: Faker) -> tuple[str, str]:
    draw = fake.name if tdef.party_kind == "person" else fake.company
    a = str(draw())
    b = str(draw())
    while b == a:
        b = str(draw())
    return a, b


def _target_pages(cfg: dict[str, Any], index: int, doc_type: str, rng: random.Random) -> int:
    name = cfg["page_count"]["function"]
    fn = PAGE_COUNT_FUNCTIONS.get(name)
    if fn is None:
        raise ValueError(
            f"unknown page_count.function {name!r}; known: {sorted(PAGE_COUNT_FUNCTIONS)}"
        )
    cap = int(cfg["type_max_pages"][doc_type])
    return fn(index, int(cfg["seed"]), doc_type, cap, rng, cfg["page_count"]["params"])


def build_spec(cfg: dict[str, Any], index: int) -> dict[str, Any]:
    seed = doc_seed(int(cfg["seed"]), index)
    rng = random.Random(seed)
    fake = Faker("en_IN")
    fake.seed_instance(seed)

    types = cfg["doc_types"]
    doc_type = types[index % len(types)]
    tdef = TYPES[doc_type]
    target = _target_pages(cfg, index, doc_type, rng)

    party_a, party_b = _draw_parties(tdef, fake)
    ctx = SlotContext(rng, fake, {"party_a": party_a, "party_b": party_b})
    blocks: list[dict[str, Any]] = []

    def add(kind: str, text: str, entities: list[dict[str, Any]]) -> None:
        blocks.append(
            {"id": f"b{len(blocks) + 1:04d}", "kind": kind, "text": text, "entities": entities}
        )

    add("title", tdef.title, [])
    for kind, tpl in tdef.header:
        add(kind, *fill(tpl, ctx))
    closing = [(kind, *fill(tpl, ctx)) for kind, tpl in tdef.closing]

    cursor = Cursor()
    for b in blocks:
        cursor = cursor.advance(block_height(b["kind"], b["text"]))

    def closing_end(c: Cursor) -> Cursor:
        for kind, text, _ in closing:
            c = c.advance(block_height(kind, text))
        return c

    number, full = 0, False
    while not full:
        for section in tdef.sections:
            number += 1
            order = list(section.clauses)
            rng.shuffle(order)
            heading = f"{number}. {section.heading}"
            for k, tpl in enumerate(order, start=1):
                text, ents = fill(f"{number}.{k} {tpl}", ctx)
                unit = [("clause", text, ents)]
                if k == 1:
                    unit.insert(0, ("heading", heading, []))
                nxt = cursor
                for kind, t, _ in unit:
                    nxt = nxt.advance(block_height(kind, t))
                if closing_end(nxt).page > target:
                    full = True
                    break
                cursor = nxt
                for kind, t, e in unit:
                    add(kind, t, e)
            if full:
                break
    for kind, text, ents in closing:
        add(kind, text, ents)

    spec: dict[str, Any] = {
        "spec_version": SPEC_VERSION,
        "doc_id": f"doc_{index:04d}",
        "index": index,
        "doc_type": doc_type,
        "seed": seed,
        "page_count_function": cfg["page_count"]["function"],
        "target_pages": target,
        "page_count": 0,
        "title": tdef.title,
        "blocks": blocks,
    }
    spec["page_count"] = _measure_pages(spec)
    return spec


def _measure_pages(spec: dict[str, Any]) -> int:
    c = Cursor()
    for b in spec["blocks"]:
        c = c.advance(block_height(b["kind"], b["text"]))
    return c.page


def generate_one(cfg: dict[str, Any], index: int) -> tuple[dict[str, Any], bytes]:
    spec = build_spec(cfg, index)
    return spec, render_pdf(spec)


def generate_corpus(cfg: dict[str, Any], out_dir: Path, indices: list[int] | None = None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = range(int(cfg["n_docs"])) if indices is None else indices
    n = 0
    for i in todo:
        spec, pdf = generate_one(cfg, i)
        (out_dir / f"{spec['doc_id']}.pdf").write_bytes(pdf)
        (out_dir / f"{spec['doc_id']}.json").write_text(dump_spec(spec), encoding="utf-8")
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=EVAL_DIR / "configs" / "default.yaml")
    ap.add_argument("--seed", type=int, help="override config seed")
    ap.add_argument("--n-docs", type=int, help="override config n_docs")
    ap.add_argument("--out", type=Path, help="override config corpus_dir")
    ap.add_argument("--index", type=int, nargs="*", help="generate only these document indices")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.n_docs is not None:
        cfg["n_docs"] = args.n_docs
    out = args.out or (EVAL_DIR / cfg["corpus_dir"])
    n = generate_corpus(cfg, out, args.index)
    print(f"wrote {n} documents to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
