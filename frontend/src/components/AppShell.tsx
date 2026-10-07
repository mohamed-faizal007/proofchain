import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ThemeToggle } from "./ThemeToggle";

export function AppShell({ children }: { children: ReactNode }): ReactElement {
  const { user } = useAuth();
  return (
    <>
      <header className="flex items-center justify-between gap-4 border-b bg-white px-6 py-3 text-sm shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <nav aria-label="Main" className="flex items-center gap-4">
          <Link to="/" className="text-lg font-bold tracking-tight">
            ProofChain
          </Link>
          <Link to="/verify" className="hover:underline">
            Verify a document
          </Link>
          {user && (
            <Link to="/verifications" className="hover:underline">
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
