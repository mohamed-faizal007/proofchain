# ProofChain demo runbook

A script for presenting the demo from the opening line to the closing line. Every button, field and
heading below is the label the frontend shows today (checked against `frontend/src`). For what each
verdict means see the [user guide](USER_GUIDE.md); for the reasoning behind the answers to likely
questions see [PROJECT_EXPLAINED.md](PROJECT_EXPLAINED.md) sections 13 and 14.

## Before the audience arrives

Do these on the presenting machine, in this order. Allow time: the first build of the backend image
is 15 to 30 minutes; later runs reuse it.

1. Start **Docker Desktop** and wait until it reports running.
2. From the repo root run `.\scripts\demo.ps1`. Use `-Reset` only if the chain container was
   recreated or you want a clean database, and `-Build` only after code changes.
3. The script must end with **Demo is up.** and a table of 7 verdicts, all matching their expected
   value. The line `health: status=ok mongo=ok s3=ok chain=ok` must show `chain=ok`; if it does not,
   approvals would not anchor, so fix that before presenting.
4. Open http://127.0.0.1:8080 in a normal window and a **second, private window** (or a second browser
   profile). Reason: the header has no sign-out button, so one window cannot switch users without
   clearing the `proofchain_token` entry in local storage. Keep the issuer in one window and the
   approver in the other.
5. The files are in `demo\data`. Open that folder in Explorer so you can drag files into the page.

Logins: `issuer@proofchain.local`, `approver@proofchain.local`, `admin@proofchain.local`. Password:
`$env:SEED_PASSWORD` if you set one, otherwise `proofchain-demo-1` (public dev default). The app
opens in dark theme; the toggle at the right of the header switches to light.

## The demo files and their expected result

The seeded document is **Demo Lease Agreement (ProofChain)**, type CONTRACT, with version 1 (original)
and version 2 (change note "Amendment: lease term extended"), both approved and anchored.

| File | What it is | Banner shown | Raw verdict | What to point at |
|---|---|---|---|---|
| `original_v1.pdf` | First approved version | Authentic, but superseded by a newer version (amber) | `AUTHENTIC_SUPERSEDED` | Byte-identical to an approved version, but version 2 is newer |
| `approved_v2.pdf` | Approved amendment, latest | Authentic: latest approved version (green) | `AUTHENTIC_LATEST` | **Chain proof** panel, transaction hash |
| `resaved_v2.pdf` | Version 2 re-saved, same text, new bytes | Content equivalent to an approved version (amber) | `CONTENT_EQUIVALENT` | Text identical, bytes differ, not called authentic |
| `tampered_amount.pdf` | Rent ₹11,700 changed to ₹16,700 | Tampered (red) | `TAMPERED` | One modified region on page 3, `AMOUNT_CHANGE` |
| `tampered_party.pdf` | Counterparty name swapped | Tampered (red) | `TAMPERED` | One region, `PARTY_CHANGE` |
| `tampered_obligation.pdf` | "shall" weakened to "may" | Tampered (red) | `TAMPERED` | One region, `OBLIGATION_CHANGE` |
| `tampered_clause_removed.pdf` | A clause deleted | Tampered (red) | `TAMPERED` | One deleted region, `CLAUSE_REMOVED` |

The four categorised tampers need the NLP image (the default build). A slim `WITH_NLP=0` image loses
`PARTY_CHANGE`. The tampered files show these results only when verified **against the lease document**
(part 3 below); anonymously or on automatic detection they come back `UNKNOWN_DOCUMENT` by design.

## Part 1. Opening (about 1 minute)

Say: "A signed PDF proves who signed it, not whether the copy in front of you is the one that was
approved. ProofChain answers four questions about a document: did it change, where, was the change
authorized, and what kind of change was it. The verdict comes from hashes and a blockchain record. The AI
only explains the change; it never decides."

Show the login page. The left panel lists the three ideas (Tamper detection, Change localization,
On-chain proof). Do not sign in yet.

## Part 2. Anyone can verify, no account (about 3 minutes)

1. Click **Verify a document** in the header. Page title: **Verify**.
2. Drag `approved_v2.pdf` into the **PDF file** drop area (or click it to browse). The page shows the file
   name and size. Leave **Explain the changes (semantic analysis)** ticked. Click **Verify**.
3. While it runs the button reads *Verifying…* and a progress bar shows upload percentage, then an
   *Analysing the document…* bar.
4. Result: green banner **Authentic: latest approved version**. Show the **Pipeline** steps and the
   **Chain proof** panel (hashes and the transaction link). Say: only hashes are on-chain, never the
   document. Anonymous reports are redacted by design.
5. Click **Verify another file** and repeat with `original_v1.pdf` (amber, superseded) and
   `resaved_v2.pdf` (amber, content equivalent).
6. Repeat with `tampered_amount.pdf`: grey **Unknown document**. Say: an anonymous user has no way to say
   which document it claims to be, so nothing is claimed. Signing in fixes that.

## Part 3. Locating the tampering (about 5 minutes)

Use the **issuer window**.

1. Open **Login**, enter the issuer email and password, click **Sign in**. You land on the **Dashboard**
   (skeleton placeholders flash while it loads). It shows *New document*, filters and the lease row.
2. Click **Verify a document**. A new field appears: **Compare against a document (optional)**.
   Choose **Demo Lease Agreement (ProofChain)**.
3. Upload `tampered_amount.pdf` and click **Verify**.
   - Red banner **Tampered**. Both PDFs are shown side by side with the changed region highlighted.
   - The **Changes** list shows the category `AMOUNT_CHANGE`, severity, before and after text and a plain
     explanation. Click a change and both viewers scroll to it.
   - Say: "The category and wording come from the NLP layer. The Tampered verdict comes from the Merkle
     tree and would be the same with the NLP switched off."
4. Click **Verify another file** and repeat with `tampered_party.pdf` (`PARTY_CHANGE`),
   `tampered_obligation.pdf` (`OBLIGATION_CHANGE`, critical) and `tampered_clause_removed.pdf`
   (`CLAUSE_REMOVED`).
5. Alternative path, if you skip the picker: with **Detect automatically** a tampered file returns
   **Unknown document** and the page asks **Which document is this file a copy of?**. Pick the lease and
   click **Verify against this document**.
6. Click **History** in the header: the verifications you just ran are listed with their verdicts; open
   one to see **Verification** details.

## Part 4. Provenance on the document page (about 2 minutes)

1. From the **Dashboard** click the lease. The document page shows type, **Latest approved version**: 2,
   the text root hash (copy button) and the **Revisions** cards for version 1 and version 2, each with
   status, anchor state and transaction link.
2. **Compare revisions** shows the change between version 1 and version 2.
3. **Provenance** lists one card per event with its type (for example the submit, approve and anchor
   events, shown by their raw event names), the time and the actor.

## Part 5. Maker and checker, live (optional, about 5 minutes)

This leaves new data behind and changes which version is latest. Run it **last**, or finish with
`.\scripts\demo.ps1 -Reset` to restore the clean state.

1. Issuer window, on the lease page, click **Submit new revision**. Enter a change note (required), choose
   `tampered_amount.pdf` as the PDF and click **Submit revision**. A toast says the revision was
   submitted and is waiting for approval; the page shows it as PENDING. Say: this stands in for a
   legitimate amendment.
2. Approver window (private), sign in as the approver. The header now has **Approvals**. Open it. The
   pending revision appears with the placeholder *Comment (required to reject, optional to approve)*.
   Click **Approve**. The status moves ANCHORING to ANCHORED after a few seconds.
3. Maker is not checker: the issuer has no **Approvals** link, and the API refuses a self-approval with
   403 `SELF_APPROVAL_FORBIDDEN`. The seed users each hold one role, so this is shown by explanation or
   with the API, not by clicking.
4. Verify `approved_v2.pdf` again: now amber **Authentic, but superseded by a newer version**, because a
   newer approved version exists.

## Part 6. Revoke and retry (optional, about 3 minutes)

- **Revoke** (approver window, on the revision card of an approved and anchored revision): click
  **Revoke**, read the warning that this cannot be undone and the reason is public, type a reason under
  **Reason (required)**, click **Confirm revoke**. A toast confirms *Version N revoked on-chain.* Verify
  that revision's file: red **Unauthorized version** with the reason. Revoking is irreversible, so do it
  only on the version added in part 5, never on the original lease unless you will `-Reset` afterwards.
- **Retry anchor** (admin only, shown on a revision whose anchor FAILED): the button reads **Retry
  anchor** and a toast says *Anchoring retry queued*. A failed anchor is hard to stage live; the API
  path (`POST /revisions/{id}/retry-anchor`) was exercised on the local stack, the button itself has not
  been clicked against a real failure.

## Part 7. Closing (about 1 minute)

Say: "Three things to take away. The verdict is cryptographic, not a model's opinion. Only fingerprints
are on-chain, so the document stays private. And the system tells you where and what kind of change
happened, which a plain hash cannot." Offer the limits honestly: text-based English PDFs only, scanned
PDFs are rejected, a single organisation, and an approval still waiting for its anchor is reported
authentic with the chain check skipped.

## If something goes wrong

| Symptom | Cause and fix |
|---|---|
| Script stops: *Port N is already in use* | Another stack holds the port. Stop it, then rerun |
| Script stops: *The chain was reset* | The Hardhat container was recreated. Run `.\scripts\demo.ps1 -Reset` |
| `chain=down` in the health line | Chain container not listening. Rerun the script; if it persists use `-Reset` |
| Approve works but the revision stays ANCHORING or goes FAILED | Chain unreachable. Restore it, then an admin uses **Retry anchor** |
| Lease verifies as **Record mismatch** | The database holds anchors for an older chain. `-Reset` |
| PDF viewer area is blank | The frontend image predates the nginx worker fix. `-Build` |
| Cannot switch user | There is no sign-out button. Use the second window, or delete `proofchain_token` from local storage |
| Sepolia demo | `-Network sepolia` has not been run live. Follow the README checklist and rehearse first |
