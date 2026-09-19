---
description: Pick the next task from TASKS.md and produce an implementation plan (no code yet)
argument-hint: "[optional TASK-ID]"
---
1. Read the "Current status" section and the LAST log entry of `PROGRESS.md`.
2. Open `TASKS.md`. If `$ARGUMENTS` is a task ID, use it; otherwise choose the first `[ ]` task whose Deps are all `[x]`.
   If its deps are not done, say so and stop.
3. Read ONLY the docs/sections listed in the task's Refs, plus the area CLAUDE.md for the folders you'll touch.
4. Mark the task `[~]` in TASKS.md.
5. Reply with a plan of at most ~15 lines:
   - Files to create/modify
   - Tests to write first (names + what they assert)
   - Commands you will run to verify
   - Any ambiguity in the spec (propose a default, flag if it needs an ADR)
6. STOP and wait for my "go".
