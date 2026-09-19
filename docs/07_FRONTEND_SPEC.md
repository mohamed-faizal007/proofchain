# 07 — Frontend Spec

Stack: React 18 + TypeScript (strict) + Vite, Tailwind CSS, React Router v6, TanStack Query v5, axios,
react-hook-form + zod, `react-pdf` (pdf.js) for rendering, lucide-react icons, Vitest + Testing Library.
Theme: clean, light/dark; verdict colours: green AUTHENTIC, amber CONTENT_EQUIVALENT/SUPERSEDED, red TAMPERED/
UNAUTHORIZED/RECORD_MISMATCH, grey UNKNOWN.

## Structure
```
src/
  api/        client.ts (axios + JWT interceptor + error envelope parsing), types.ts, hooks/*.ts (TanStack Query)
  auth/       AuthContext.tsx, ProtectedRoute.tsx, RoleGate.tsx
  components/ VerdictBanner, PipelineSteps, PdfViewerWithHighlights, ChangeList, ChangeCard,
              VersionTimeline, ProvenanceTimeline, HashBadge (truncate + copy), TxLink, FileDropzone, StatusPill
  pages/      Login, Register, Dashboard, DocumentNew, DocumentDetail, RevisionNew, ApprovalsQueue,
              Verify, VerificationDetail, VerificationHistory, NotFound
  lib/        format.ts (dates, hashes), bbox.ts (PDF points → viewport pixels)
```

## Pages
| Route | Content |
|---|---|
| `/login`, `/register` | forms |
| `/` Dashboard | counts (documents, pending approvals, recent verifications), document table with search/filter |
| `/documents/new` | upload PDF + title + type (ISSUER) |
| `/documents/:id` | header, latest approved version, **VersionTimeline** (revisions with status + anchor tx), **ProvenanceTimeline**, "Submit new revision", diff between any two revisions |
| `/approvals` | pending revisions (APPROVER); approve/reject with comment; disabled for own submissions |
| `/verify` | dropzone + optional document picker → report |
| `/verifications/:id` | **VerdictBanner**; **PipelineSteps** (file hash → text root → localization → authorization → chain → semantic); side-by-side PDF viewers (reference vs candidate) with bbox highlights coloured by region type; **ChangeList** grouped by page/section with category chips, severity, before/after token diff and explanation; clicking a change scrolls both viewers; chain proof panel with explorer link |

## Highlight overlay
Backend bboxes are PDF points `[x0,y0,x1,y1]`, top-left origin (PyMuPDF). Overlay = absolutely positioned
divs over each `<Page>` scaled by `renderedWidth / page.originalWidth`. Colours: MODIFIED amber,
INSERTED green (candidate side), DELETED red (reference side).

## Rules
- All server state via TanStack Query; no ad-hoc fetches in components.
- Role-based UI hides actions but the server is the authority.
- Show hashes truncated (`a1b2c3…f9e8`) with copy button; full value in tooltip.
- Every page handles loading, empty and error states.
