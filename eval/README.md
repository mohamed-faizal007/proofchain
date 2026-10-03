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
Rules: every script takes `--config` and `--seed`; no network access except `measure_chain.py` and `prices.py`
(explicit opt-in, never in CI); results are reproducible apart from timings and live chain data.

## Running the evaluation
`python generate_corpus.py --config configs/default.yaml`, then `python tamper.py --config configs/default.yaml`,
then `python run_eval.py --config configs/default.yaml` -> `results/seed<seed>/` (`metrics.json`, CSVs,
`latency.*`). Only the latency files change between runs. Baseline definitions are in `baselines.py`.
Every plain-diff result carries a `caveat` field (metrics.json, localization.csv): it is handed the stored
reference text and has no tamper evidence, so quote its scores only together with that caveat.

## Classification ablation (P9-04) and reproducing the real-model numbers
`run_eval.py` also classifies every localized region with three arms (`nlp_arms.py`): `rules`, `rules_ner`
(+ spaCy NER) and `rules_ner_emb` (+ MiniLM embeddings), and scores them against the tamper ground truth
(`classification.py` docstring defines "correct": strict primary category headline, lenient reported alongside,
unmatched / ambiguous regions and missed edits counted). Outputs: `classification.json`, `classification.csv`,
`classification_regions.csv`, `confusion_<arm>.csv` (deterministic) and `classification_latency.json`,
`classification_env.json` (timings, library versions). A missing model is an error, never a silent fallback
(`--no-classification` skips the ablation).

One-command reproduction on any machine with Python 3.11 (from the repo root):
```
cd backend; pip install -e ".[dev,eval,nlp]"; python -m spacy download en_core_web_sm; cd ../eval
python generate_corpus.py --config configs/default.yaml; python tamper.py --config configs/default.yaml
python run_eval.py --config configs/default.yaml        # -> results/seed<seed>/classification*.{json,csv}
```
CI does exactly this in the `eval-nlp` workflow (`.github/workflows/eval-nlp.yml`: on `eval/**`, `backend/app/nlp/**`
or `backend/proofchain_core/**` changes to main, on `v*` tags, weekly, and on demand), runs it twice, requires
byte-identical outputs and uploads them as the `eval-nlp-results` artifact. The ordinary `eval` job installs no models
and runs only fake-model tests (`pytest` deselects `-m nlp`); the real-model test is `pytest -m nlp`.

## Figures, REPORT.md and chain measurements (P9-05)
`python run_eval.py --config configs/default.yaml --report` (or `python report.py --results results/seed<seed>
--measurements measurements/seed<seed>`) writes `figures/*.png|pdf` (efficiency, latency, localization,
classification, chain) and `REPORT.md` from the result files only: offline, no clock, byte-identical for identical
inputs. A missing optional input (classification, chain) gives a "not run" section. The plain-diff caveat is
printed under every localization table.

`measure_chain.py` is the only script that spends gas (needs `CHAIN_RPC_URL`, `ANCHOR_PRIVATE_KEY`, and a deployed
registry; `--target local` against `npx hardhat node`, `--target sepolia` for the live run). `--dry-run` prints the
plan, the cap and the balance and sends nothing. The plan is 10 first versions plus 5 second versions (15
transactions); `chain.max_transactions` (20) is a hard cap: a larger plan is refused before the first send, there is
no retry, a failure stops the run, and after the run the cap is re-checked against the sender's on-chain nonce. The
run records the balance before and after and checks it against the receipts. Each run also takes a price snapshot
(`prices.py`: mainnet gas price from a public RPC, ETH/USD/INR from CoinGecko; any field that cannot be fetched falls
back to the config default and the report then labels the cost figures ILLUSTRATIVE, NOT CURRENT). Output goes to
`measurements/seed<seed>/` (committed: live Sepolia numbers cannot be regenerated). Gas used does not depend on the
gas price; latency is the wall time of `anchor_version` including 2 confirmations on Sepolia.

## Setup and determinism
`cd backend; pip install -e ".[dev,eval]"` (Faker is pinned exactly). Run from `eval/`:
`python generate_corpus.py --config configs/default.yaml` and `python -m pytest -q`.
PDFs embed the pinned DejaVu Sans files in `templates/fonts/` (SHA-256 checked in `render.py`);
output bytes depend on the reportlab, PyMuPDF, Faker and font pins. Each document is a pure function
of `(config, seed, index)`; the page-count distribution is the named function in `configs/default.yaml`.
