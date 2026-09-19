---
description: Gate review at the end of a phase
argument-hint: "<phase, e.g. P1>"
---
Review phase $ARGUMENTS:
1. List every task of the phase in TASKS.md with status. Any not `[x]` → report and stop.
2. Run the complete test suites for all areas (including coverage for backend).
3. Use the `code-reviewer` subagent on the files changed in this phase (`git log` to find them).
   For P1 also use the `spec-guardian` subagent.
4. Produce a short report: passing checks, findings by severity, spec drift, tech debt.
5. Fix HIGH findings now (each as a small commit `$ARGUMENTS-review: …`). Log MEDIUM/LOW under
   "Known issues" in PROGRESS.md.
6. Suggest a git tag, e.g. `git tag v0.<n>-$ARGUMENTS`.
