import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useVerification } from "../api/hooks/verifications";
import { Alert } from "../components/Alert";
import { PageHeader } from "../components/PageHeader";
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
    <main className="mx-auto max-w-[88rem] px-4 py-8 sm:px-6">
      <PageHeader
        icon="shield"
        title="Verification"
        actions={
          <Link to="/verifications" className="btn-secondary">
            All verifications
          </Link>
        }
      />
      <div className="mt-6">
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
