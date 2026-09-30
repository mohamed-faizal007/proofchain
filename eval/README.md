# eval — research evaluation harness

Spec: `docs/08_TESTING_AND_EVAL.md` §C. Uses `proofchain_core` directly (install backend with `pip install -e ../backend[dev,nlp]`).

```
eval/
  configs/default.yaml     # seed, corpus size, page counts, ops, repetitions
  templates/               # contract/invoice/certificate templates (Jinja-like python dicts)
  generate_corpus.py       # -> data/corpus/{id}.pdf + {id}.json
  tamper.py                # -> data/tamper/{case}.pdf + {case}.json (ground truth) + manifest.json
  run_eval.py              # -> results/<timestamp>/metrics.json, *.csv, figures/*.png, REPORT.md
  baselines.py             # whole-file hash, plain diff, positional chunk compare
```
Rules: every script takes `--config` and `--seed`; no network access; results are reproducible.

## Setup and determinism
`cd backend; pip install -e ".[dev,eval]"` (Faker is pinned exactly). Run from `eval/`:
`python generate_corpus.py --config configs/default.yaml` and `python -m pytest -q`.
PDFs embed the pinned DejaVu Sans files in `templates/fonts/` (SHA-256 checked in `render.py`);
output bytes depend on the reportlab, PyMuPDF, Faker and font pins. Each document is a pure function
of `(config, seed, index)`; the page-count distribution is the named function in `configs/default.yaml`.
