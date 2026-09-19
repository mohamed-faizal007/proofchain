# 08 — Testing Strategy & Research Evaluation

## A. Testing pyramid
| Layer | Tooling | Where | Must cover |
|---|---|---|---|
| Core unit | pytest + **hypothesis** | `backend/tests/unit/core` | canonicalization table tests; chunking boundaries; leaf/node domain separation; Merkle root/proof for n=1..33; odd promotion; proof verification; determinism (build twice, JSON round-trip); localization for modify/insert/delete/multi-page/page-count change/identical/content-equivalent |
| Property tests | hypothesis | same | any single-leaf change ⇒ root changes; every proof verifies; tampered proof fails; localize(tree, tree) = IDENTICAL; localize finds exactly the mutated chunk for random single mutations |
| App unit | pytest, fakes | `tests/unit/app` | services with FakeRegistryClient, moto S3, mongomock-motor; role and state-machine rules |
| API integration | httpx AsyncClient + ASGI | `tests/integration` | full flows: register → approve → anchor → verify each verdict |
| E2E chain | pytest `@pytest.mark.chain` | `tests/integration/chain` | against running Hardhat node + deployed contract (skipped unless `CHAIN_E2E=1`) |
| Contract | Hardhat + chai | `contracts/test` | see 05 |
| Frontend | Vitest + Testing Library | `frontend/src/**/*.test.tsx` | bbox scaling, VerdictBanner mapping, API error parsing, auth guard |

Fixtures: `backend/tests/fixtures/make_fixtures.py` generates PDFs with **reportlab** from Python specs
(committed outputs in `tests/fixtures/pdfs/`, regenerated only intentionally). Include: 1-page, 3-page contract
with numbered headings, a document with ligatures/smart quotes/NBSP, an image-only PDF (for NO_EXTRACTABLE_TEXT),
an encrypted PDF, a non-PDF file.

Coverage gates: `proofchain_core` ≥ 90 % (`--cov-fail-under` in a dedicated CI job), app ≥ 75 %.
Markers: `nlp`, `chain`, `slow` excluded by default (`addopts = -m "not nlp and not chain and not slow"`).

## B. CI (GitHub Actions `.github/workflows/ci.yml`)
Jobs: `backend` (ruff, mypy, pytest + coverage), `contracts` (hardhat test), `frontend` (lint, typecheck, vitest, build).
ubuntu-latest **and** windows-latest for the core tests (determinism across OS).

## C. Research evaluation (`eval/`)
Produces the tables/figures for the results chapter. Everything seeded and config-driven.

### C.1 Corpus (`eval/generate_corpus.py`)
- Base documents: templated contracts (lease, service agreement, NDA), invoices and certificates generated with
  Faker (`en_IN` locale for ₹ amounts and Indian names) and rendered with reportlab; 1–50 pages; target 200 base docs.
- Optional real text: CUAD contract texts rendered to PDF (cite dataset in report).
- Each base doc is also exported as a structured JSON spec so tamper operations are exact.

### C.2 Tamper operations (`eval/tamper.py`) — ground truth recorded per case
| Op | Expected category | Method |
|---|---|---|
| change amount | AMOUNT_CHANGE | spec edit + re-render, and in-place PyMuPDF redact+insert |
| change date | DATE_CHANGE | both |
| change party name | PARTY_CHANGE | both |
| change percentage / number | PERCENTAGE_CHANGE / NUMBER_CHANGE | spec |
| flip obligation (shall→may, insert "not") | OBLIGATION_CHANGE | spec |
| insert clause | CLAUSE_ADDED | spec (shifts later content — tests alignment) |
| delete clause | CLAUSE_REMOVED | spec |
| reword clause | CLAUSE_MODIFIED | spec (paraphrase templates) |
| typo fix | MINOR_EDIT | spec |
| metadata only / re-save | none → CONTENT_EQUIVALENT | PyMuPDF `set_metadata` + save with different options |
| multi-edit (2–5 ops) | multiple | spec |
Ground truth: set of changed chunk ids (derived by building trees of the spec text), pages, categories.

### C.3 Metrics (`eval/run_eval.py` → `eval/results/<run>/`)
- Detection rate (file hash, text root) — expect 100 %; false-positive rate on metadata-only cases — expect 0 %.
- Localization precision/recall/F1 at page level and chunk level; split by op and by in-place vs re-render.
- Merkle efficiency: hash comparisons (fast path & descent) vs naive full chunk comparison, vs page count.
- Classification: per-category P/R/F1, macro-F1, confusion matrix; ablation rules vs rules+embeddings.
- Latency: build tree, localize, NLP, end-to-end verify vs pages (1, 5, 10, 25, 50, 100); median of 5 runs.
- Chain: gas per `anchorVersion` (v1 vs subsequent), USD/INR cost estimate at a stated gas price; anchoring latency on Sepolia (n≥10).
- Baselines: (1) whole-file SHA-256 (detection only, no localization); (2) plain text diff without hashing
  (time + no tamper-evidence); (3) positional chunk comparison without alignment (shows insertion cascade).
Outputs: `metrics.json`, CSVs, and matplotlib PNG/PDF figures; `REPORT.md` auto-summarizing the run.
