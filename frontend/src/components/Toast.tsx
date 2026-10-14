import type { ReactElement, ReactNode } from "react";
import { useCallback, useMemo, useRef, useState } from "react";
import { prefersReducedMotion } from "../lib/motion";
import { ToastContext, type ToastApi } from "./useToast";

const TOAST_MS = 4500;
const EXIT_MS = 160;

interface ToastItem {
  id: number;
  message: string;
  leaving: boolean;
}

/** Lightweight success toasts that survive route changes (mounted in the shell, above the routes). */
export function ToastProvider({ children }: { children: ReactNode }): ReactElement {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const dismiss = useCallback(
    (id: number) => {
      if (prefersReducedMotion()) {
        remove(id);
        return;
      }
      setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
      window.setTimeout(() => remove(id), EXIT_MS);
    },
    [remove],
  );

  const notify = useCallback(
    (message: string) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-2), { id, message, leaving: false }]);
      window.setTimeout(() => dismiss(id), TOAST_MS);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`alert alert-success pointer-events-auto bg-white shadow-lg dark:bg-gray-900 ${
              t.leaving ? "animate-toast-out" : "animate-toast-in"
            }`}
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="mt-px h-4 w-4 shrink-0"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M8 12.5l2.7 2.7L16 9.5 M12 21a9 9 0 100-18 9 9 0 000 18z" />
            </svg>
            <p className="min-w-0 flex-1">{t.message}</p>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(t.id)}
              className="-mr-1 rounded px-1 font-semibold opacity-70 hover:opacity-100"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
