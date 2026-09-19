import type { FutureConfig } from "react-router-dom";

/** Opt in to React Router v7 behaviour early (silences the v6 future-flag warnings). */
export const routerFuture: Partial<FutureConfig> = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
};
