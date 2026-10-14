import type { ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { LoadingRegion, Skeleton } from "../components/Skeleton";
import { useAuth } from "./AuthContext";

/** Gates a route to signed-in users. UX only: the server enforces the real authorization. */
export function ProtectedRoute({ children }: { children: ReactElement }): ReactElement {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <LoadingRegion label="Loading…" className="mx-auto max-w-6xl space-y-4 px-6 py-10">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-32 w-full rounded-2xl" />
      </LoadingRegion>
    );
  }

  if (!user) {
    const from = `${location.pathname}${location.search}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }

  return children;
}
