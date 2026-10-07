import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ThemeToggle } from "./ThemeToggle";

const NAV_LINK =
  "rounded-lg px-3 py-1.5 font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white";

export function AppShell({ children }: { children: ReactNode }): ReactElement {
  const { user } = useAuth();
  return (
    <>
      <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-gray-200 bg-white/80 px-6 py-3 text-sm backdrop-blur-md dark:border-gray-700/70 dark:bg-gray-950/70">
        <nav aria-label="Main" className="flex items-center gap-1">
          <Link
            to="/"
            className="mr-4 flex items-center gap-2 font-display text-xl font-bold tracking-tight"
          >
            <span
              aria-hidden="true"
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-400 to-blue-700 text-sm text-white shadow-glow"
            >
              ✓
            </span>
            <span>
              Proof<span className="text-blue-600 dark:text-blue-300">Chain</span>
            </span>
          </Link>
          <Link to="/verify" className={NAV_LINK}>
            Verify a document
          </Link>
          {user && (
            <Link to="/verifications" className={NAV_LINK}>
              History
            </Link>
          )}
        </nav>
        <ThemeToggle />
      </header>
      {children}
    </>
  );
}
