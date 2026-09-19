---
description: Verify, record progress and commit the current task
---
For the task currently marked `[~]` in TASKS.md:
1. Run the full check for every area you touched (see "Common commands" in root CLAUDE.md and the area CLAUDE.md).
   Fix failures. Do not skip or delete tests to make them pass.
2. Re-read the task's Accept criteria and confirm each one explicitly (✅/❌). If any ❌, fix or report — don't mark done.
3. Mark the task `[x]` in TASKS.md; update "Current status" in PROGRESS.md (phase, next task).
4. Append a PROGRESS.md log entry using the template (keep it under 10 lines).
5. `git add -A` and `git commit -m "<TASK-ID>: <short summary>"`.
6. Print the next task ID and suggest I run `/clear` before `/next-task`.
