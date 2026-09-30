# Frontend rules (React + TS + Vite)

- Spec: `docs/07_FRONTEND_SPEC.md`; API shapes: `docs/04_API_SPEC.md` mirrored in `src/api/types.ts`.
- TypeScript strict, no `any`. Server state only through TanStack Query hooks in `src/api/hooks/`.
- Components are small and presentational; pages compose them. Tailwind only (no CSS frameworks added).
- Every page handles loading / empty / error. Never trust role checks client-side for security.
- Before finishing: `npm run lint; npm run typecheck; npm run test; npm run build`.
- Do not add new dependencies without noting why in PROGRESS.md.
- Never render user-supplied or server-supplied content with `dangerouslySetInnerHTML` (XSS). The JWT is kept in
  `localStorage` (see PROGRESS.md "P8-01" for the tradeoff), which is readable by any script on the page, so this
  rule is load-bearing, not stylistic.
- Import the PDF viewer only via `components/LazyPdfViewer.tsx`, never `PdfViewerWithHighlights` or `pdfjs-dist` directly (keeps pdf.js out of the main bundle). Enforced by `src/chunkSplit.test.ts`.
- If the full suite shows many random timeouts (`Test timed out in 5000ms`, `findBy*` failures across unrelated files), the machine is contended (backend pytest, Docker, a live-check browser, low free RAM); re-run with `npx vitest run --maxWorkers=4` or `--no-file-parallelism` before suspecting the tests (see PROGRESS.md, P8-07 follow-up).
