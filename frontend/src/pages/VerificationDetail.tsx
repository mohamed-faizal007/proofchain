import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useVerification } from "../api/hooks/verifications";
import { Alert } from "../components/Alert";
import { LoadingRegion, Skeleton } from "../components/Skeleton";
import { VerificationReportView } from "../components/VerificationReportView";

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "You don't have access to this verification.";
    if (err.status === 404) return "Verification not found.";
    return err.message;
  }
  return "Something went wrong.";
}

/** A stored report. The uploaded file is never stored, so no candidate viewer here. */
export function VerificationDetail(): ReactElement {
  const { id } = useParams();
  const query = useVerification(id);

  return (
    <main className="mx-auto max-w-6xl p-6">
      <h1 className="page-title">Verification</h1>
      <p className="mt-1 text-sm">
        <Link to="/verifications" className="link underline">
          All verifications
        </Link>
      </p>
      <div className="mt-4">
        {query.isLoading ? (
          <LoadingRegion label="Loading verification…" className="space-y-5">
            <Skeleton className="h-32 w-full rounded-2xl" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Skeleton className="h-36 w-full rounded-2xl" />
              <Skeleton className="h-36 w-full rounded-2xl" />
            </div>
          </LoadingRegion>
        ) : query.isError ? (
          <Alert>{errorMessage(query.error)}</Alert>
        ) : query.data ? (
          <VerificationReportView report={query.data} isAnonymous={false} />
        ) : null}
      </div>
    </main>
  );
}
