# ProofChain user guide

A short guide for the people who use the web app. For how it works inside, see
[PROJECT_EXPLAINED.md](PROJECT_EXPLAINED.md); for scripting against the API, see
[API_EXAMPLES.md](API_EXAMPLES.md).

Start the app with `.\scripts\demo.ps1` (see the [README](../README.md)), then open
http://127.0.0.1:8080. The demo logins are `issuer@proofchain.local`, `approver@proofchain.local` and
`admin@proofchain.local`; the password is printed by the script. The app opens in dark theme; the
toggle in the header switches to light.

## Roles

| Role | Can do |
|---|---|
| **Issuer** | Register documents, submit new revisions, view their own history |
| **Approver** | Approve or reject pending revisions submitted by someone else; revoke an anchored revision (API only) |
| **Admin** | Retry a failed anchor (API only) |
| **Anyone, signed in or not** | Verify a PDF (anonymous reports are redacted) |

The person who submitted a revision can never approve it (maker is not checker).

## 1. Register a document (issuer)

1. Sign in, choose **New document**.
2. Enter a title and document type and upload the PDF. It must contain real text; scanned images are rejected.
3. The document is created with revision 1 in status **PENDING**. Nothing is on the chain yet.

To change a document later, submit a new revision with the updated PDF and a change note (required);
it is also PENDING. **Known gap:** the web app's *Submit new revision* page is a placeholder ("Not
implemented yet"). Submit revisions through the API (`POST /documents/{id}/revisions`, see
[API_EXAMPLES.md](API_EXAMPLES.md)); `demo.ps1` does this for the amendment.

## 2. Approve and anchor (approver)

1. Sign in as an approver (a different person from the submitter) and open **Approvals**.
2. For each pending revision, add a comment (optional to approve, **required to reject**) and choose Approve or Reject.
3. On approval the revision becomes **APPROVED** and is anchored in the background. Its status moves
   from ANCHORING to **ANCHORED** once the transaction is confirmed (a few seconds on the local chain).
   Only the hashes are written to the chain, never the document.
4. If anchoring fails the revision shows FAILED; an admin retries it through the API (`POST /revisions/{id}/retry-anchor`).

The document page shows every revision, its status, the transaction hash and the provenance events.

## 3. Verify a file (anyone)

1. Open **Verify**, upload the PDF you were given.
2. Leave **Detect automatically** on, or pick the document the file claims to be a copy of.
3. Read the verdict banner and the pipeline steps under it.

If you are signed in and the file matches no stored version, the result is `UNKNOWN_DOCUMENT` and the
page asks *"Which document is this file a copy of?"*. Choose it and the same file is checked against
that document; a file that was altered then comes back `TAMPERED` with the changes highlighted.

### Verdicts

| Verdict | Colour | Meaning |
|---|---|---|
| `AUTHENTIC_LATEST` | green | Byte-identical to the newest approved version, and it matches the on-chain record |
| `AUTHENTIC_SUPERSEDED` | amber | Byte-identical to an approved version, but a newer approved version exists |
| `CONTENT_EQUIVALENT` | amber | The text is identical to an approved version, but the file bytes differ (for example re-saved with new metadata). Not called authentic |
| `TAMPERED` | red | The text differs from the approved version. The report lists each change |
| `UNAUTHORIZED_VERSION` | red | The file matches a revision that was never approved, was rejected or was revoked |
| `RECORD_MISMATCH` | red | The database and the on-chain record disagree. Overrides every other verdict |
| `UNKNOWN_DOCUMENT` | grey | The file matches nothing stored and no document was chosen |

If the blockchain node cannot be reached, the chain check is skipped and says so; an outage is never
reported as tampering.

### Reading a TAMPERED report

- Both PDFs are shown side by side. Highlights mark the changed regions (modified, inserted or deleted).
- The **change list** shows, per region, a category (for example `AMOUNT_CHANGE`, `PARTY_CHANGE`,
  `OBLIGATION_CHANGE`, `CLAUSE_REMOVED`), a severity, the before and after text and a plain-language
  explanation. Clicking a change scrolls both viewers to it.
- The categories and explanations come from the NLP layer. They help you read the change; the
  tampered verdict itself comes from the hashes and the Merkle tree and is never altered by the NLP.
- The **chain proof** panel shows whether the stored hashes match the on-chain record and links to the
  transaction.

## 4. History and revocation

- **History** lists your past verifications with their verdicts.
- An approver can revoke an anchored revision through the API (`POST /revisions/{id}/revoke`; there is no button yet). After that, its file is reported `UNAUTHORIZED_VERSION`.

## Try it with the demo files

`demo.ps1` writes sample PDFs to `demo/data`. Walkthrough with the expected result for each file:
[PROJECT_EXPLAINED.md section 13](PROJECT_EXPLAINED.md#13-demo-walkthrough). In short: `original_v1.pdf`
is authentic but superseded, `approved_v2.pdf` is the latest and authentic, `resaved_v2.pdf` is content
equivalent, and the four `tampered_*.pdf` files are tampered, each with one highlighted region.
