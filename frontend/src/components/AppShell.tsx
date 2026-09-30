import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ThemeToggle } from "./ThemeToggle";

export function AppShell({ children }: { children: ReactNode }): ReactElement {
  const { user } = useAuth();
  return (
    <>
      <header className="flex items-center justify-between gap-4 border-b px-6 py-2 text-sm dark:border-gray-700">
        <nav aria-label="Main" className="flex items-center gap-4">
          <Link to="/" className="font-semibold">
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
