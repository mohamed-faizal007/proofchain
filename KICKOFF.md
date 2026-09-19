# KICKOFF — how to build ProofChain A→Z with Claude Code in VS Code

## 0. One-time setup (≈20 min, you do this)
1. Install: Git, Python 3.11, Node 20 LTS, Docker Desktop, VS Code + Claude Code extension.
2. Create the repo and drop this pack in:
   ```powershell
   mkdir ProofChain; cd ProofChain
   # copy/unzip the pack here
   git init; git add -A; git commit -m "chore: planning pack"
   Copy-Item .env.example .env        # fill values later; Claude cannot read .env (by design)
   ```
3. Open the folder in VS Code, open Claude Code. **Do not run `/init`** — `CLAUDE.md` already exists and is tuned.
4. Optional: push to a private GitHub repo so CI runs (Claude is denied `git push`; you push).

## 1. First session — let Claude challenge the plan (plan mode)
Switch to **plan mode** (Shift+Tab until it shows plan mode) and paste:
> Read CLAUDE.md, TASKS.md and every file in docs/ (docs/project_report.md is our original report).
> Do not write code. Report: (1) contradictions between docs, (2) anything in the report not covered by
> TASKS.md, (3) risky or ambiguous specs with your proposed default, (4) any library version you'd pin.
> Keep it under 40 lines.

Resolve the findings (accept/adjust), let Claude apply the doc edits, commit `docs: kickoff review`.

## 2. The loop (repeat for every task)
```
/clear                      ← fresh context each task; PROGRESS.md carries memory
/next-task                  ← Claude picks the task, reads only its refs, posts a plan, waits
  review the plan → "go"    (or correct it; small corrections are cheap here, expensive later)
  Claude writes tests → code → runs checks
/finish-task                ← verifies acceptance, updates TASKS/PROGRESS, commits
```
At the end of each phase: `/phase-review P1` (etc.), then `git tag` as suggested, then push.

## 3. Phase order & rough effort
| Phase | What | Sessions | Checkpoint you should see |
|---|---|---|---|
| P0 | Scaffold, tooling, infra, CI | 6 | health endpoint, `hardhat test`, Vite page, containers up |
| P1 | **Integrity core** (hash, Merkle, localize) | 9 | CLI prints roots; tamper test localizes 1 chunk |
| P2–P3 | Mongo, S3, auth | 7 | login works in `/docs` Swagger |
| P4 | Contract + chain client | 3 | anchoring on local node from a Python test |
| P5 | Documents, maker–checker, anchoring | 6 | upload → approve → tx hash visible |
| P6 | Verification pipeline | 4 | every verdict reproducible via Swagger |
| P7 | NLP | 4 | "amount changed from ₹50,000 to ₹80,000" |
| P8 | Frontend | 7 | highlighted tamper on side-by-side PDFs |
| P9 | Evaluation | 5 | metrics.json + figures for the results chapter |
| P10 | Hardening, Sepolia, demo | 5 | public explorer links; demo script |
P1 is where correctness is won or lost — review those plans carefully. P9 can start right after P1 in parallel
by a teammate (it only depends on `proofchain_core`).

## 4. Rules of thumb for driving Claude Code efficiently
- **One task per session, `/clear` between tasks.** Long sessions drift; PROGRESS.md is the handoff.
- **Plan mode for anything touching `proofchain_core`, the contract, or auth.** Auto-accept edits is fine for UI polish.
- **Say "go" only when the plan names tests.** If a plan has no tests, ask for them.
- **Never let it change `docs/02_ALGORITHMS.md` without an ADR.** If it proposes one, that's a real decision — read it.
- **When it loops on the same error twice**, stop it (Esc), run `/debug <symptom>` in a fresh session.
- **Keep secrets out of chat.** You fill `.env`; Claude only edits `.env.example`.
- **Start chain-dependent sessions with infra running:** `docker compose -f infra/docker-compose.yml up -d` and
  `cd contracts; npx hardhat node` in a separate terminal.
- **Use `@file` references** in prompts (e.g. `@docs/04_API_SPEC.md`) instead of pasting content.
- **Commit after every task** so you can `git revert` a bad session cheaply.
- If a task feels too big for one session (> ~30 min of Claude work), ask Claude to split it in TASKS.md first.

## 5. Useful ad-hoc prompts
- "Use the spec-guardian subagent to audit proofchain_core."
- "Use the code-reviewer subagent on the last 3 commits."
- "/sync-docs" after API or schema changes.
- "Generate a tampered copy of tests/fixtures/pdfs/contract_3p.pdf changing the rent amount, then run the CLI
  localizer against the original and explain the output."
- "Write the Results chapter draft from eval/results/<run>/REPORT.md in the same style as docs/project_report.md."

## 6. Team split (optional, 3 people)
- Person A: P1 core + P6 verification + P9 evaluation (research spine).
- Person B: P2/P3/P5 backend services + P4 contract + P10 deploy.
- Person C: P0-05 + P8 frontend + P7 NLP.
Each person runs their own Claude Code on a feature branch; merge via PR after `/phase-review`.
Keep TASKS.md as the single board — mark `[~] (name)` when you take a task.
