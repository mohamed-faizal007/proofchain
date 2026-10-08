# ProofChain API examples

Real requests and responses captured from a running local stack (`demo.ps1`, Hardhat chain) on
2026-10-08, in the order of a normal workflow. Reference: [04_API_SPEC.md](04_API_SPEC.md); interactive docs
at http://127.0.0.1:8000/docs.

**How these were produced and trimmed**

- Tokens and passwords are masked (`<JWT>`, `<PASSWORD>`). Everything else is as returned, including ids and
  the local-chain transaction hashes, which are throwaway values.
- To keep it readable, fields that do not matter for the example are removed (timestamps, sizes, counters,
  timings, token-level diffs, bounding boxes) and long lists are cut to two items followed by `"..."`.
  Use `/docs` for the full schemas.
- The example PDFs are one-page generated agreements, not the demo lease.
- Not captured: `revoke` and `retry-anchor` (they change state that the demo relies on); see the table below.

**Setup used in the snippets** (PowerShell; `curl.exe`, not the `curl` alias, handles file uploads):

```powershell
$api = 'http://127.0.0.1:8000/api/v1'
$issuerHeaders   = @{ Authorization = "Bearer $issuerToken" }     # from POST /auth/login
$approverHeaders = @{ Authorization = "Bearer $approverToken" }
$headers = $issuerHeaders   # any signed-in user; also $token = $login.access_token for curl.exe
```

Roles in the demo: `issuer@proofchain.local` (ISSUER), `approver@proofchain.local` (APPROVER),
`admin@proofchain.local` (ADMIN). The submitter of a revision cannot approve or reject it.

## Endpoints not shown above

| Call | Who | Notes |
|---|---|---|
| `POST /revisions/{id}/reject` | approver | JSON `{"comment": "..."}`, comment required |
| `POST /revisions/{id}/revoke` | approver | JSON `{"reason": "..."}`; only an anchored revision; the reason is stored on-chain (public) |
| `POST /revisions/{id}/retry-anchor` | admin | Retries a `FAILED` anchor; idempotent (checks the chain first) |
| `GET /revisions/{id}/download` | any signed-in | Streams the stored PDF |
| `GET /revisions/{id}/diff?against={id}` | any signed-in | Localization and analysis between two revisions |
| `GET /verifications/{id}` | owner or admin | Full stored report |

The web app has no UI for submitting a revision, revoking or retrying an anchor; use these API calls.

## Walkthrough

### Health

No token needed.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Response `200`:

```json
{
  "status": "ok",
  "mongo": "ok",
  "s3": "ok",
  "chain": "ok",
  "nlp": "not_configured",
  "canon_version": 2
}
```

### Register

Public in dev; creates a user with the `VERIFIER` role. In prod only an admin can register users.

```powershell
$body = @{ email = 'example.978cab@example.com'; password = '<PASSWORD>'; full_name = 'Example Verifier' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $api/auth/register -ContentType 'application/json' -Body $body
```

Response `201`:

```json
{
  "id": "339df119-4ef3-444b-bf13-da05f6713ccc",
  "email": "example.978cab@example.com",
  "full_name": "Example Verifier",
  "roles": [
    "VERIFIER"
  ]
}
```

### Login

Returns a bearer token (masked here). Send it as `Authorization: Bearer <token>`.

```powershell
$body = @{ email = 'issuer@proofchain.local'; password = '<PASSWORD>' } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri $api/auth/login -ContentType 'application/json' -Body $body
$h = @{ Authorization = "Bearer $($login.access_token)" }
```

Response `200`:

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "user": {
    "id": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
    "email": "issuer@proofchain.local",
    "full_name": "Demo Issuer",
    "roles": [
      "ISSUER"
    ]
  }
}
```

### Create a document (issuer)

Multipart upload. Creates the document and revision 1 in status `PENDING`. Nothing is on the chain yet.

```powershell
curl.exe -X POST $api/documents -H "Authorization: Bearer $token" `
  -F "file=@agreement_v1.pdf" -F "title=Service Agreement (API example)" -F "doc_type=CONTRACT"
```

Response `201`:

```json
{
  "document": {
    "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "title": "Service Agreement (API example)",
    "doc_type": "CONTRACT",
    "latest_approved_revision_id": null,
    "latest_approved_version_no": null,
    "revision_count": 1
  },
  "revision": {
    "id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
    "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "revision_no": 1,
    "change_note": null,
    "status": "PENDING",
    "version_no": null,
    "submitted_by": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
    "review_comment": null,
    "file_hash": "252480986fa3f26a80a424a9f00eb93ba8bb852b08374ada507324b858f27b5c",
    "text_root": "1e982f94d9bcfe1e7327440a67e1571585a0f28b6fb6c926721df9dc0f49161b",
    "canon_version": 2,
    "anchor": {
      "status": "NOT_REQUESTED",
      "tx_hash": null,
      "block_number": null,
      "error": null
    },
    "revocation": null
  }
}
```

### Approvals queue (approver)

Pending revisions across all documents, oldest first. Approver or admin only.

```powershell
Invoke-RestMethod "$api/revisions?status=PENDING" -Headers $approverHeaders
```

Response `200`:

```json
{
  "items": [
    {
      "id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
      "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
      "revision_no": 1,
      "change_note": null,
      "status": "PENDING",
      "version_no": null,
      "submitted_by": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
      "review_comment": null,
      "file_hash": "252480986fa3f26a80a424a9f00eb93ba8bb852b08374ada507324b858f27b5c",
      "text_root": "1e982f94d9bcfe1e7327440a67e1571585a0f28b6fb6c926721df9dc0f49161b",
      "canon_version": 2,
      "anchor": {
        "status": "NOT_REQUESTED",
        "tx_hash": null,
        "block_number": null,
        "error": null
      },
      "revocation": null,
      "document_title": "Service Agreement (API example)"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### Error envelope

Every 4xx/5xx has the same shape. Here the issuer tries to approve (only approvers can).

```powershell
Invoke-RestMethod -Method Post -Uri $api/revisions/86b6902a-ca16-486d-ad7b-9e2bb086aa18/approve -Headers $issuerHeaders -ContentType 'application/json' -Body '{}'
```

Response `403`:

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Insufficient role",
    "details": {
      "required_any_of": [
        "APPROVER"
      ]
    }
  }
}
```

### Approve (approver)

Returns `202` right away; anchoring runs in the background (`anchor.status` is `ANCHORING`).

```powershell
Invoke-RestMethod -Method Post -Uri $api/revisions/86b6902a-ca16-486d-ad7b-9e2bb086aa18/approve -Headers $approverHeaders `
  -ContentType 'application/json' -Body '{"comment":"Reviewed."}'
```

Response `202`:

```json
{
  "id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
  "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
  "revision_no": 1,
  "change_note": null,
  "status": "APPROVED",
  "version_no": null,
  "submitted_by": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
  "review_comment": "Reviewed.",
  "file_hash": "252480986fa3f26a80a424a9f00eb93ba8bb852b08374ada507324b858f27b5c",
  "text_root": "1e982f94d9bcfe1e7327440a67e1571585a0f28b6fb6c926721df9dc0f49161b",
  "canon_version": 2,
  "anchor": {
    "status": "ANCHORING",
    "tx_hash": null,
    "block_number": null,
    "error": null
  },
  "revocation": null
}
```

### Poll the revision until anchored

After a few seconds `status` is `APPROVED` and `anchor.status` is `ANCHORED` with the transaction hash.

```powershell
Invoke-RestMethod $api/revisions/86b6902a-ca16-486d-ad7b-9e2bb086aa18 -Headers $approverHeaders
```

Response `200`:

```json
{
  "id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
  "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
  "revision_no": 1,
  "change_note": null,
  "status": "APPROVED",
  "version_no": 1,
  "submitted_by": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
  "review_comment": "Reviewed.",
  "file_hash": "252480986fa3f26a80a424a9f00eb93ba8bb852b08374ada507324b858f27b5c",
  "text_root": "1e982f94d9bcfe1e7327440a67e1571585a0f28b6fb6c926721df9dc0f49161b",
  "canon_version": 2,
  "anchor": {
    "status": "ANCHORED",
    "tx_hash": "0x5f4cabd855caf05aaa32604cce037f4eb253419f3d2d4d2899a1654f83b9c604",
    "block_number": 4,
    "error": null
  },
  "revocation": null
}
```

### Submit a new revision (issuer) — API only

The web app's *Submit new revision* page is a placeholder, so this call is the only way to submit a revision (`demo.ps1` uses it too). `change_note` is required; the parent is the latest approved revision. 409 if one is already pending, 422 if the text did not change.

```powershell
curl.exe -X POST $api/documents/b6975ed4-8e75-482a-8886-7d32e542f70d/revisions -H "Authorization: Bearer $token" `
  -F "file=@agreement_v2.pdf" -F "change_note=Extend the term to 24 months."
```

Response `201`:

```json
{
  "document": {
    "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "title": "Service Agreement (API example)",
    "doc_type": "CONTRACT",
    "latest_approved_revision_id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
    "latest_approved_version_no": 1,
    "revision_count": 2
  },
  "revision": {
    "id": "c4fa3a8c-779d-4fec-8b96-2af8e2516f3f",
    "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "revision_no": 2,
    "change_note": "Extend the term to 24 months.",
    "status": "PENDING",
    "version_no": null,
    "submitted_by": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
    "review_comment": null,
    "file_hash": "80592a71f6402c7424f99516cd61cff70a6c878033b507f61a52047f84b160f7",
    "text_root": "5932c2f630e715ecd9c7d015580708b93eae1df6eabd13946d92a9a748dc123f",
    "canon_version": 2,
    "anchor": {
      "status": "NOT_REQUESTED",
      "tx_hash": null,
      "block_number": null,
      "error": null
    },
    "revocation": null
  }
}
```

### Get a document

Returns the document and its latest approved revision.

```powershell
Invoke-RestMethod $api/documents/b6975ed4-8e75-482a-8886-7d32e542f70d -Headers $headers
```

Response `200`:

```json
{
  "document": {
    "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "title": "Service Agreement (API example)",
    "doc_type": "CONTRACT",
    "latest_approved_revision_id": "c4fa3a8c-779d-4fec-8b96-2af8e2516f3f",
    "latest_approved_version_no": 2,
    "revision_count": 2
  },
  "latest_approved_revision": {
    "id": "c4fa3a8c-779d-4fec-8b96-2af8e2516f3f",
    "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "revision_no": 2,
    "change_note": "Extend the term to 24 months.",
    "status": "APPROVED",
    "version_no": 2,
    "submitted_by": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
    "review_comment": "Reviewed.",
    "file_hash": "80592a71f6402c7424f99516cd61cff70a6c878033b507f61a52047f84b160f7",
    "text_root": "5932c2f630e715ecd9c7d015580708b93eae1df6eabd13946d92a9a748dc123f",
    "canon_version": 2,
    "anchor": {
      "status": "ANCHORED",
      "tx_hash": "0x6d0c6aa532db1bdc6c9bdc5f93d98f25568ee7c0920e0377d263f18ec27b9244",
      "block_number": 5,
      "error": null
    },
    "revocation": null
  }
}
```

### Provenance events

The tamper-evident event log; `chain_valid` is the hash-chain check of the events.

```powershell
Invoke-RestMethod $api/documents/b6975ed4-8e75-482a-8886-7d32e542f70d/provenance -Headers $headers
```

Response `200`:

```json
{
  "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
  "chain_valid": true,
  "events": [
    {
      "id": "baebe016-1129-48ab-a97a-834f57db6a70",
      "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
      "revision_id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
      "type": "DOCUMENT_CREATED",
      "actor_id": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
      "at": "2026-10-08T15:49:22.060000Z",
      "data": {
        "title": "Service Agreement (API example)",
        "doc_type": "CONTRACT"
      },
      "prev_event_hash": null,
      "event_hash": "2958f9bb28558f25cb3aff668ed8c5859a2de7181f7bb6f4d0d7a1da14e2e942"
    },
    {
      "id": "8036a419-8a55-4972-a3ee-949fba14041b",
      "document_id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
      "revision_id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
      "type": "REVISION_SUBMITTED",
      "actor_id": "c7e9b43b-639b-4f39-ac18-8d1d8e143364",
      "at": "2026-10-08T15:49:22.063000Z",
      "data": {
        "revision_no": 1,
        "file_hash": "252480986fa3f26a80a424a9f00eb93ba8bb852b08374ada507324b858f27b5c",
        "text_root": "1e982f94d9bcfe1e7327440a67e1571585a0f28b6fb6c926721df9dc0f49161b",
        "change_note": null
      },
      "prev_event_hash": "2958f9bb28558f25cb3aff668ed8c5859a2de7181f7bb6f4d0d7a1da14e2e942",
      "event_hash": "d04fe72d5de74bac7a23b7715e9f7f37beebcbb73c21830483a3c92636a08d62"
    },
    "..."
  ]
}
```

### Verify an authentic file

The unmodified latest version. `document_id` is optional; without it the file is matched by hash.

```powershell
curl.exe -X POST $api/verify -H "Authorization: Bearer $token" -F "file=@agreement_v2.pdf"
```

Response `200`:

```json
{
  "id": "01525d75-c2e3-4262-979b-6f3ebdb9c0a6",
  "at": "2026-10-08T15:49:26.578000Z",
  "verdict": "AUTHENTIC_LATEST",
  "summary": "Byte-identical to the latest approved version, revision 2 (v2) of 'Service Agreement (API example)'",
  "document": {
    "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "title": "Service Agreement (API example)"
  },
  "matched_revision": {
    "id": "c4fa3a8c-779d-4fec-8b96-2af8e2516f3f",
    "revision_no": 2,
    "version_no": 2,
    "status": "APPROVED",
    "anchored_tx": "0x6d0c6aa532db1bdc6c9bdc5f93d98f25568ee7c0920e0377d263f18ec27b9244",
    "revocation": null
  },
  "reference_revision": null,
  "steps": [
    {
      "name": "FILE_HASH",
      "status": "PASS"
    },
    {
      "name": "TEXT_ROOT",
      "status": "PASS"
    },
    "..."
  ],
  "candidate": {
    "filename": "agreement_v2.pdf",
    "file_hash": "80592a71f6402c7424f99516cd61cff70a6c878033b507f61a52047f84b160f7",
    "text_root": "5932c2f630e715ecd9c7d015580708b93eae1df6eabd13946d92a9a748dc123f"
  },
  "localization": null,
  "analysis": null,
  "chain_check": {
    "performed": true,
    "ok": true,
    "reason": null,
    "mismatches": [],
    "tx_hash": "0x6d0c6aa532db1bdc6c9bdc5f93d98f25568ee7c0920e0377d263f18ec27b9244"
  }
}
```

### Verify an older approved version

Byte-identical to an approved version, but a newer one exists.

```powershell
curl.exe -X POST $api/verify -H "Authorization: Bearer $token" -F "file=@agreement_v1.pdf"
```

Response `200`:

```json
{
  "id": "71a01633-fa07-4ad0-8a65-7e0be712d5db",
  "at": "2026-10-08T15:49:26.665000Z",
  "verdict": "AUTHENTIC_SUPERSEDED",
  "summary": "Byte-identical to approved revision 1 (v1); a newer approved version exists of 'Service Agreement (API example)'",
  "document": {
    "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "title": "Service Agreement (API example)"
  },
  "matched_revision": {
    "id": "86b6902a-ca16-486d-ad7b-9e2bb086aa18",
    "revision_no": 1,
    "version_no": 1,
    "status": "APPROVED",
    "anchored_tx": "0x5f4cabd855caf05aaa32604cce037f4eb253419f3d2d4d2899a1654f83b9c604",
    "revocation": null
  },
  "reference_revision": null,
  "steps": [
    {
      "name": "FILE_HASH",
      "status": "PASS"
    },
    {
      "name": "TEXT_ROOT",
      "status": "PASS"
    },
    "..."
  ],
  "candidate": {
    "filename": "agreement_v1.pdf",
    "file_hash": "252480986fa3f26a80a424a9f00eb93ba8bb852b08374ada507324b858f27b5c",
    "text_root": "1e982f94d9bcfe1e7327440a67e1571585a0f28b6fb6c926721df9dc0f49161b"
  },
  "localization": null,
  "analysis": null,
  "chain_check": {
    "performed": true,
    "ok": true,
    "reason": null,
    "mismatches": [],
    "tx_hash": "0x5f4cabd855caf05aaa32604cce037f4eb253419f3d2d4d2899a1654f83b9c604"
  }
}
```

### Verify a tampered file

The fee was altered. Passing `document_id` names the document it claims to be a copy of; without it a file that matches no stored hash is `UNKNOWN_DOCUMENT` by design. The report is trimmed here.

```powershell
curl.exe -X POST $api/verify -H "Authorization: Bearer $token" -F "file=@agreement_v2_altered.pdf" -F "document_id=b6975ed4-8e75-482a-8886-7d32e542f70d"
```

Response `200`:

```json
{
  "id": "4c1df5ad-0dd1-4693-8514-72711cbfffec",
  "at": "2026-10-08T15:49:26.890000Z",
  "verdict": "TAMPERED",
  "summary": "1 change on page(s) 1 vs approved revision 2 (v2)",
  "document": {
    "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "title": "Service Agreement (API example)"
  },
  "matched_revision": null,
  "reference_revision": {
    "id": "c4fa3a8c-779d-4fec-8b96-2af8e2516f3f",
    "revision_no": 2,
    "version_no": 2,
    "status": "APPROVED",
    "anchored_tx": "0x6d0c6aa532db1bdc6c9bdc5f93d98f25568ee7c0920e0377d263f18ec27b9244",
    "revocation": null
  },
  "steps": [
    {
      "name": "FILE_HASH",
      "status": "FAIL"
    },
    {
      "name": "TEXT_ROOT",
      "status": "FAIL"
    },
    "..."
  ],
  "candidate": {
    "filename": "agreement_v2_altered.pdf",
    "file_hash": "9013f9812f3b1ae9d973c71c7b492b5391dbee1c16fad75f031949d93c31dc78",
    "text_root": "ce83dd0417de6f161688e136942ab7e514201d9704f59274a421e8673dbaa661"
  },
  "localization": {
    "status": "CHANGED",
    "regions": [
      {
        "id": "r1",
        "type": "MODIFIED",
        "ref_chunk_id": "p0-c3",
        "cand_chunk_id": "p0-c3",
        "ref_page": 0,
        "cand_page": 0,
        "ref_text": "3. Fees. Beta Logistics shall pay a monthly fee of INR 10,000 on the first day of each month.",
        "cand_text": "3. Fees. Beta Logistics shall pay a monthly fee of INR 90,000 on the first day of each month.",
        "section_id": "S0",
        "section_title": "Preamble"
      }
    ],
    "method": "MERKLE_FAST_PATH",
    "stats": {
      "modified": 1,
      "inserted": 0,
      "deleted": 0
    }
  },
  "analysis": [
    {
      "region_id": "r1",
      "primary_category": "AMOUNT_CHANGE",
      "categories": [
        "AMOUNT_CHANGE"
      ],
      "severity": "HIGH",
      "entity_changes": [
        {
          "type": "MONEY",
          "before": "INR:10000.00",
          "after": null
        },
        {
          "type": "MONEY",
          "before": null,
          "after": "INR:90000.00"
        }
      ],
      "explanation": "In Section \"Preamble\", page 1: the amount changed from INR:10000.00 to INR:90000.00.",
      "method": "RULES+EMBEDDINGS"
    }
  ],
  "chain_check": {
    "performed": true,
    "ok": true,
    "reason": null,
    "mismatches": [],
    "tx_hash": "0x6d0c6aa532db1bdc6c9bdc5f93d98f25568ee7c0920e0377d263f18ec27b9244"
  }
}
```

### Verify anonymously

No token. With public verification on (the demo default) anyone can verify. For a tampered file an anonymous report is redacted (ADR-021: no stored reference text) and an unmatched file is always `UNKNOWN_DOCUMENT`.

```powershell
curl.exe -X POST $api/verify -F "file=@agreement_v2.pdf"
```

Response `200`:

```json
{
  "id": "8b047369-5155-436e-bb05-7d0c16dd491d",
  "at": "2026-10-08T15:49:26.950000Z",
  "verdict": "AUTHENTIC_LATEST",
  "summary": "Byte-identical to the latest approved version, revision 2 (v2) of 'Service Agreement (API example)'",
  "document": {
    "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
    "title": "Service Agreement (API example)"
  },
  "matched_revision": {
    "id": "c4fa3a8c-779d-4fec-8b96-2af8e2516f3f",
    "revision_no": 2,
    "version_no": 2,
    "status": "APPROVED",
    "anchored_tx": "0x6d0c6aa532db1bdc6c9bdc5f93d98f25568ee7c0920e0377d263f18ec27b9244",
    "revocation": null
  },
  "reference_revision": null,
  "steps": [
    {
      "name": "FILE_HASH",
      "status": "PASS"
    },
    {
      "name": "TEXT_ROOT",
      "status": "PASS"
    },
    "..."
  ],
  "candidate": {
    "filename": "agreement_v2.pdf",
    "file_hash": "80592a71f6402c7424f99516cd61cff70a6c878033b507f61a52047f84b160f7",
    "text_root": "5932c2f630e715ecd9c7d015580708b93eae1df6eabd13946d92a9a748dc123f"
  },
  "localization": null,
  "analysis": null,
  "chain_check": {
    "performed": true,
    "ok": true,
    "reason": null,
    "mismatches": [],
    "tx_hash": "0x6d0c6aa532db1bdc6c9bdc5f93d98f25568ee7c0920e0377d263f18ec27b9244"
  }
}
```

### Verification history

Your own past verifications, newest first, paginated.

```powershell
Invoke-RestMethod "$api/verifications?page=1&page_size=3" -Headers $headers
```

Response `200`:

```json
{
  "items": [
    {
      "id": "4c1df5ad-0dd1-4693-8514-72711cbfffec",
      "at": "2026-10-08T15:49:26.890000Z",
      "verdict": "TAMPERED",
      "summary": "1 change on page(s) 1 vs approved revision 2 (v2)",
      "document": {
        "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
        "title": "Service Agreement (API example)"
      },
      "filename": "agreement_v2_altered.pdf",
      "file_hash": "9013f9812f3b1ae9d973c71c7b492b5391dbee1c16fad75f031949d93c31dc78"
    },
    {
      "id": "71a01633-fa07-4ad0-8a65-7e0be712d5db",
      "at": "2026-10-08T15:49:26.665000Z",
      "verdict": "AUTHENTIC_SUPERSEDED",
      "summary": "Byte-identical to approved revision 1 (v1); a newer approved version exists of 'Service Agreement (API example)'",
      "document": {
        "id": "b6975ed4-8e75-482a-8886-7d32e542f70d",
        "title": "Service Agreement (API example)"
      },
      "filename": "agreement_v1.pdf",
      "file_hash": "252480986fa3f26a80a424a9f00eb93ba8bb852b08374ada507324b858f27b5c"
    },
    "..."
  ],
  "page": 1,
  "page_size": 3,
  "total": 3
}
```

### Missing token

Protected routes answer 401 without a bearer token.

```powershell
Invoke-RestMethod $api/documents
```

Response `401`:

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required",
    "details": {}
  }
}
```
