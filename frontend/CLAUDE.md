# Frontend rules (React + TS + Vite)

- Spec: `docs/07_FRONTEND_SPEC.md`; API shapes: `docs/04_API_SPEC.md` mirrored in `src/api/types.ts`.
- TypeScript strict, no `any`. Server state only through TanStack Query hooks in `src/api/hooks/`.
- Components are small and presentational; pages compose them. Tailwind only (no CSS frameworks added).
- Every page handles loading / empty / error. Never trust role checks client-side for security.
- Before finishing: `npm run lint; npm run typecheck; npm run test; npm run build`.
- Do not add new dependencies without noting why in PROGRESS.md.
