import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useVerification } from "../api/hooks/verifications";
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
      <h1 className="text-2xl font-semibold">Verification</h1>
      <p className="mt-1 text-sm">
        <Link to="/verifications" className="text-blue-600 underline">
          All verifications
        </Link>
      </p>
      <div className="mt-4">
        {query.isLoading ? (
          <p role="status" className="text-sm text-gray-500">
            Loading verification…
          </p>
        ) : query.isError ? (
          <p role="alert" className="text-sm text-red-600">
            {errorMessage(query.error)}
          </p>
        ) : query.data ? (
          <VerificationReportView report={query.data} isAnonymous={false} />
        ) : null}
      </div>
    </main>
  );
}
