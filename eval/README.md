# eval — research evaluation harness

Spec: `docs/08_TESTING_AND_EVAL.md` §C. Uses `proofchain_core` directly (install backend with `pip install -e ../backend[dev,nlp]`).

```
eval/
  configs/default.yaml     # seed, corpus size, page counts, ops, repetitions
  templates/               # contract/invoice/certificate templates (Jinja-like python dicts)
  generate_corpus.py       # -> data/corpus/{id}.pdf + {id}.json
  tamper.py                # -> data/tampered/{case}.pdf + ground_truth.jsonl
  run_eval.py              # -> results/<timestamp>/metrics.json, *.csv, figures/*.png, REPORT.md
  baselines.py             # whole-file hash, plain diff, positional chunk compare
```
Rules: every script takes `--config` and `--seed`; no network access; results are reproducible.
