import type { ReactElement } from "react";
import { useState } from "react";
import { ApiError } from "../api/client";
import { useRetryAnchor, useRevokeRevision } from "../api/hooks/revisions";
import type { Revision } from "../api/types";
import { useAuth } from "../auth/AuthContext";

const MAX_REASON = 500;

function revokeErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "Revoking requires the APPROVER role.";
    switch (err.code) {
      case "REVISION_NOT_APPROVED":
        return "Only an approved revision can be revoked (it may already be revoked).";
      case "CONFLICT":
        return "This revision is not anchored on-chain yet, so it cannot be revoked.";
      case "CHAIN_UNAVAILABLE":
        return "The blockchain is unreachable right now. Nothing was revoked; try again later.";
      default:
        return err.message;
    }
  }
  return "Revoke failed. Please try again.";
}

function retryErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "Retrying an anchor requires the ADMIN role.";
    return err.message;
  }
  return "Retry failed. Please try again.";
}

/** Revoke (APPROVER, APPROVED + ANCHORED) and retry-anchor (ADMIN, anchor FAILED) for one
 * revision. Role and state checks only hide buttons; the backend is the authority. */
export function RevisionActions({ revision }: { revision: Revision }): ReactElement | null {
  const { user } = useAuth();
  const revoke = useRevokeRevision();
  const retry = useRetryAnchor();
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const canRevoke =
    !!user?.roles.includes("APPROVER") &&
    revision.status === "APPROVED" &&
    revision.anchor.status === "ANCHORED";
  const canRetry =
    !!user?.roles.includes("ADMIN") &&
    revision.status === "APPROVED" &&
    revision.anchor.status === "FAILED";

  if (!canRevoke && !canRetry && !error && !notice) return null;

  async function confirmRevoke(): Promise<void> {
    const trimmed = reason.trim();
    if (!trimmed) {
      setReasonError("A reason is required.");
      return;
    }
    setError(null);
    try {
      await revoke.mutateAsync({ revisionId: revision.id, reason: trimmed });
      setConfirming(false);
      setReason("");
    } catch (err) {
      setError(revokeErrorMessage(err));
    }
  }

  async function retryAnchor(): Promise<void> {
    setError(null);
    setNotice(null);
    try {
      await retry.mutateAsync(revision.id);
      setNotice("Retry queued. The anchor status will update shortly.");
    } catch (err) {
      setError(retryErrorMessage(err));
    }
  }

  return (
    <div className="mt-3 space-y-2">
      {revision.anchor.status === "FAILED" && revision.anchor.error && canRetry && (
        <p className="text-red-600 dark:text-red-400">Anchoring failed: {revision.anchor.error}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {canRetry && (
          <button
            type="button"
            className="btn-secondary text-xs"
            disabled={retry.isPending}
            onClick={() => void retryAnchor()}
          >
            {retry.isPending ? "Retrying…" : "Retry anchor"}
          </button>
        )}
        {canRevoke && !confirming && (
          <button
            type="button"
            className="btn-secondary text-xs"
            onClick={() => {
              setConfirming(true);
              setError(null);
            }}
          >
            Revoke
          </button>
        )}
      </div>

      {canRevoke && confirming && (
        <form
          className="space-y-2 rounded border border-red-300 p-3 dark:border-red-800"
          onSubmit={(e) => {
            e.preventDefault();
            void confirmRevoke();
          }}
          noValidate
        >
          <p className="text-red-600 dark:text-red-400">
            Revoking version {revision.revision_no} marks it REVOKED on the blockchain. This cannot
            be undone, and the reason is stored on-chain, so it is public.
          </p>
          <label htmlFor={`revoke-reason-${revision.id}`} className="block text-sm font-medium">
            Reason (required)
          </label>
          <textarea
            id={`revoke-reason-${revision.id}`}
            className="w-full rounded border px-3 py-2"
            maxLength={MAX_REASON}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setReasonError(null);
            }}
          />
          {reasonError && <p className="text-red-600 dark:text-red-400">{reasonError}</p>}
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-xs" disabled={revoke.isPending}>
              {revoke.isPending ? "Revoking…" : "Confirm revoke"}
            </button>
            <button
              type="button"
              className="btn-secondary text-xs"
              disabled={revoke.isPending}
              onClick={() => {
                setConfirming(false);
                setReason("");
                setReasonError(null);
                setError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-gray-500 dark:text-gray-400">
          {notice}
        </p>
      )}
    </div>
  );
}
