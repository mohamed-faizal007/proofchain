# ProofChain

Blockchain-anchored framework for verifiable document provenance and AI-assisted tamper localization.

**Stack:** FastAPI (Python 3.11) · MongoDB · S3 (MinIO locally) · Solidity/Hardhat (local node → Sepolia) · React + TypeScript + Vite · spaCy / sentence-transformers.

## This repository starts as a planning pack
Before any code exists, the repo contains everything Claude Code needs to build the project
end to end:

| File | Purpose |
|---|---|
| `CLAUDE.md` (+ per-area CLAUDE.md) | Standing instructions auto-loaded by Claude Code |
| `KICKOFF.md` | **Start here.** Exactly how to drive Claude Code from task 1 to demo |
| `TASKS.md` | Ordered backlog, 56 tasks in 11 phases (P0–P10), each with acceptance criteria |
| `PROGRESS.md` | Session log / handoff memory between Claude Code sessions |
| `docs/project_report.md` | Original project report (chapters 1–2) |
| `docs/00–09` | PRD, architecture, algorithms, data model, API, contract, NLP, frontend, testing/eval, ADRs |
| `.claude/` | Permissions, custom slash commands, review subagents |
| `infra/docker-compose.yml`, `.env.example` | Local infrastructure and configuration contract |

## Quick start (after Phase 0 is built)
```powershell
docker compose -f infra/docker-compose.yml up -d
cd contracts; npm install; npx hardhat run scripts/deploy.ts --network localhost; cd ..
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[dev,nlp]"; uvicorn app.main:app --reload
cd frontend; npm install; npm run dev
```

Team: Ekanath (23MIA1023) · Mohamed Faizal (23MIA1133) · Rohan Julius Preetan (23MIA1160)
