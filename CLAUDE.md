# ProofChain — Instructions for Claude Code

ProofChain is a blockchain-anchored framework for verifiable document provenance and
AI-assisted tamper localization of text-based PDFs. It answers: *did this document change,
where, was the change authorized, and what kind of change was it?*

## Source of truth (read in this order when you need context)
1. `PROGRESS.md` — what is done, what is in progress, known issues. ALWAYS read the last entry first.
2. `TASKS.md` — the ordered backlog. Work on exactly one task at a time.
3. `docs/` — specs. Read only the files a task lists under **Refs**.
   - `00_PRD.md` requirements · `01_ARCHITECTURE.md` components & flows
   - `02_ALGORITHMS.md` hashing/Merkle/localization (**normative, highest-risk spec**)
   - `03_DATA_MODEL.md` · `04_API_SPEC.md` · `05_SMART_CONTRACT.md` · `06_NLP_SPEC.md`
   - `07_FRONTEND_SPEC.md` · `08_TESTING_AND_EVAL.md` · `09_DECISIONS.md` (ADRs)
   - `project_report.md` — the original academic report (motivation, objectives, literature). Background only.

## Non-negotiable invariants
- **Crypto decides, AI explains.** NLP output never changes a verification verdict.
- **Documents never go on-chain.** Chain stores only docId, file hash, text Merkle root, prev root, canon version, timestamp.
- **Determinism.** `proofchain_core` must produce identical hashes for identical input on every OS/run.
  No randomness, no dict-order dependence, no locale dependence. Canonicalization is versioned (`CANON_VERSION`).
- **Spec first.** If code and `02_ALGORITHMS.md` disagree, the spec wins. To change the spec, add an ADR
  to `docs/09_DECISIONS.md` and bump `CANON_VERSION` — never silently.
- `proofchain_core` is a pure library: no FastAPI, Mongo, S3, web3 or network imports.
- Only APPROVED revisions are anchored on-chain. Maker (submitter) ≠ checker (approver).
- Never commit secrets. Never read `.env`. Use `.env.example` for new variables.

## Repo layout
```
backend/            FastAPI app (app/) + pure integrity library (proofchain_core/) + tests/
contracts/          Hardhat + Solidity (ProofChainRegistry)
frontend/           React + TypeScript + Vite + Tailwind
eval/               Tamper corpus generator + evaluation harness (produces paper results)
infra/              docker-compose (MongoDB, MinIO, Hardhat node)
docs/               Specs and ADRs
```
Each of backend/, contracts/, frontend/ has its own CLAUDE.md with area-specific rules.

## Environment (developer machine = Windows + PowerShell + Python venv + Docker Desktop)
- Python 3.11, Node 20 LTS.
- Use PowerShell syntax in commands. Activate venv: `.\.venv\Scripts\Activate.ps1` (from backend/).
- Prefer `python -m pytest`, `python -m ruff`, `python -m mypy` over bare tool names.
- Use `pathlib` everywhere in Python; never hard-code `/` or `\` separators.
- Infra: `docker compose -f infra/docker-compose.yml up -d`

## Common commands
| Area | Command |
|---|---|
| Backend tests | `cd backend; python -m pytest -q` |
| Core tests only | `cd backend; python -m pytest tests/unit/core -q` |
| Lint/format | `cd backend; python -m ruff check . --fix; python -m ruff format .` |
| Types | `cd backend; python -m mypy proofchain_core app` |
| Run API | `cd backend; uvicorn app.main:app --reload` |
| Contracts | `cd contracts; npx hardhat test` |
| Deploy local | `cd contracts; npx hardhat run scripts/deploy.ts --network localhost` |
| Frontend | `cd frontend; npm run dev` / `npm run test` / `npm run lint` |
| Eval | `cd eval; python run_eval.py --config configs/default.yaml` |

## Working protocol (every task)
1. Read last entry of `PROGRESS.md`, then the task in `TASKS.md` and its Refs.
2. Post a short plan (files, tests, verification commands). Wait for approval if in plan mode.
3. Write tests first for anything in `proofchain_core`, services, and the contract.
4. Implement the smallest change that meets the acceptance criteria. No scope creep —
   note ideas under "Follow-ups" in PROGRESS.md instead.
5. Run the area's tests + lint + types. Fix until green.
6. Tick the task in `TASKS.md`, append an entry to `PROGRESS.md`, commit as `<TASK-ID>: <summary>`.

## Code conventions
- Python: type hints everywhere, Pydantic v2 models, async I/O in `app/`, sync pure functions in `proofchain_core`.
  Services hold business logic; routers are thin; repositories own Mongo access.
- Errors: raise domain exceptions (`app/errors.py`), mapped to the error envelope in `04_API_SPEC.md`.
- Hashes are lowercase hex strings (64 chars) in Python/JSON/Mongo, `bytes32` on-chain, `0x`-prefixed only at the web3 boundary.
- TypeScript: strict mode, no `any`, API types generated or hand-written in `src/api/types.ts` mirroring `04_API_SPEC.md`.
- Keep files < ~300 lines; split modules rather than growing them.

## When stuck
If the same failure persists after two fix attempts, stop, summarize the hypothesis and evidence,
and ask instead of trying random changes.
