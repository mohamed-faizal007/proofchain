---
description: Structured debugging for a failing test or bug
argument-hint: "<failing test or symptom>"
---
Problem: $ARGUMENTS
1. Reproduce with the smallest command; paste the exact error.
2. List up to 3 hypotheses ranked by likelihood with the evidence for each.
3. Test the top hypothesis with a targeted check (print, small script, narrower test) — no speculative edits.
4. Apply the minimal fix and add a regression test that fails before the fix.
5. If two attempts fail, stop and summarize findings for me instead of continuing.
