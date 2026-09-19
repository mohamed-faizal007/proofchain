# Backend rules (FastAPI + proofchain_core)

- Activate venv first: `.\.venv\Scripts\Activate.ps1`. Install: `pip install -e ".[dev]"` (add `,nlp` for NLP work).
- `proofchain_core/` = pure, sync, deterministic. Allowed imports: stdlib, `pymupdf`. Nothing from `app`.
  Any behaviour change here must match `docs/02_ALGORITHMS.md` exactly — cite the section in a comment.
- `app/` layering: `api/v1` (thin routers, DTO validation, auth deps) → `services/` (logic, transactions,
  provenance events) → `repositories/`, `storage/`, `chain/`, `nlp/`. Routers never touch Motor/boto3/web3.
- Dependencies are injected via `app/deps.py` so tests can swap `FakeRegistryClient`, moto S3, mongomock-motor, stub NLP.
- Every state change in a service writes a provenance event in the same function.
- CPU-heavy work (tree building, NLP) in async routes: run via `await anyio.to_thread.run_sync(...)`.
- Tests: `python -m pytest -q` (fast suite). `-m chain` needs Hardhat node + deployed contract; `-m nlp` needs models.
- Before finishing: `python -m ruff check . --fix; python -m ruff format .; python -m mypy proofchain_core app; python -m pytest -q`.
