import type { ReactElement } from "react";
import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApproveRevision, usePendingRevisions, useRejectRevision } from "../api/hooks/revisions";
import { ApiError } from "../api/client";
import type { PendingRevision } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { formatDate } from "../lib/format";

const PAGE_SIZE = 20;
const MAX_COMMENT_LENGTH = 2000;

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

function reviewErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "REVISION_NOT_PENDING") return "Someone else already reviewed this revision.";
    if (err.code === "SELF_APPROVAL_FORBIDDEN") return "You cannot review your own submission.";
    return err.message;
  }
  return "Something went wrong.";
}

export function ApprovalsQueue(): ReactElement {
  const { user } = useAuth();
  const isApprover = user?.roles.includes("APPROVER") ?? false;

  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);

  const queueQuery = usePendingRevisions({ page, page_size: PAGE_SIZE }, { enabled: isApprover });
  const approve = useApproveRevision();
  const reject = useRejectRevision();

  const [comments, setComments] = useState<Record<string, string>>({});
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Synchronous guard: React state updates are not visible until the next render, so two clicks
  // dispatched back-to-back (a genuine double click) must be caught here, not by `disabled` alone.
  const busyRef = useRef<Set<string>>(new Set());

  function setPage(next: number): void {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      params.set("page", String(next));
      return params;
    });
  }

  function setComment(id: string, value: string): void {
    setComments((prev) => ({ ...prev, [id]: value.slice(0, MAX_COMMENT_LENGTH) }));
  }

  async function handleApprove(item: PendingRevision): Promise<void> {
    if (busyRef.current.has(item.id)) return;
    busyRef.current.add(item.id);
    setBusyId(item.id);
    setStatusMessage(null);
    setRowErrors((prev) => ({ ...prev, [item.id]: "" }));
    try {
      const comment = (comments[item.id] ?? "").trim();
      await approve.mutateAsync({ revisionId: item.id, comment: comment || undefined });
      setStatusMessage(
        `Approved v${item.revision_no} of "${item.document_title ?? "this document"}". Anchoring is in progress.`,
      );
    } catch (err) {
      setRowErrors((prev) => ({ ...prev, [item.id]: reviewErrorMessage(err) }));
      if (err instanceof ApiError && err.code === "REVISION_NOT_PENDING") {
        void queueQuery.refetch();
      }
    } finally {
      busyRef.current.delete(item.id);
      setBusyId(null);
    }
  }

  async function handleReject(item: PendingRevision): Promise<void> {
    if (busyRef.current.has(item.id)) return;
    const comment = (comments[item.id] ?? "").trim();
    if (!comment) {
      setRowErrors((prev) => ({ ...prev, [item.id]: "A comment is required to reject." }));
      return;
    }
    busyRef.current.add(item.id);
    setBusyId(item.id);
    setStatusMessage(null);
    setRowErrors((prev) => ({ ...prev, [item.id]: "" }));
    try {
      await reject.mutateAsync({ revisionId: item.id, comment });
      setStatusMessage(
        `Rejected v${item.revision_no} of "${item.document_title ?? "this document"}".`,
      );
    } catch (err) {
      setRowErrors((prev) => ({ ...prev, [item.id]: reviewErrorMessage(err) }));
      if (err instanceof ApiError && err.code === "REVISION_NOT_PENDING") {
        void queueQuery.refetch();
      }
    } finally {
      busyRef.current.delete(item.id);
      setBusyId(null);
    }
  }

  if (!isApprover) {
    return (
      <main className="p-6">
        <h1 className="text-2xl font-semibold">Approvals</h1>
        <p className="mt-2 text-sm text-gray-500">
          This page requires the APPROVER role. ADMIN accounts can manage anchoring and user roles
          but are not approvers, so they cannot review revisions here.
        </p>
      </main>
    );
  }

  const totalPages = queueQuery.data
    ? Math.max(1, Math.ceil(queueQuery.data.total / PAGE_SIZE))
    : 1;

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-2xl font-semibold">Approvals</h1>
      <p className="mt-1 text-sm text-gray-500">
        Pending revisions across all documents, oldest first. You cannot review a revision you
        submitted yourself.
      </p>

      {statusMessage && (
        <p
          role="status"
          className="mt-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-800"
        >
          {statusMessage}
        </p>
      )}

      <section className="mt-6">
        {queueQuery.isLoading ? (
          <p className="text-sm text-gray-500">Loading approvals…</p>
        ) : queueQuery.isError ? (
          <p role="alert" className="text-sm text-red-600">
            {errorMessage(queueQuery.error)}
          </p>
        ) : queueQuery.data && queueQuery.data.items.length === 0 ? (
          <p className="text-sm text-gray-500">No pending revisions.</p>
        ) : (
          <ul className="space-y-4">
            {queueQuery.data?.items.map((item) => {
              const ownSubmission = user?.id === item.submitted_by;
              const busy = busyId === item.id;
              return (
                <li key={item.id} className="rounded border p-4 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Link
                      to={`/documents/${item.document_id}`}
                      className="font-medium hover:underline"
                    >
                      {item.document_title ?? "Untitled document"}
                    </Link>
                    <span className="text-gray-500">v{item.revision_no}</span>
                  </div>
                  <p className="mt-1 text-gray-500">
                    Submitted {formatDate(item.submitted_at)} by {item.submitted_by}
                    {item.change_note ? ` — ${item.change_note}` : ""}
                  </p>

                  {ownSubmission ? (
                    <p className="mt-2 text-gray-500">
                      You submitted this revision; another APPROVER must review it.
                    </p>
                  ) : (
                    <div className="mt-3">
                      <label className="sr-only" htmlFor={`comment-${item.id}`}>
                        Comment for revision {item.revision_no}
                      </label>
                      <textarea
                        id={`comment-${item.id}`}
                        value={comments[item.id] ?? ""}
                        onChange={(e) => setComment(item.id, e.target.value)}
                        maxLength={MAX_COMMENT_LENGTH}
                        rows={2}
                        placeholder="Comment (required to reject, optional to approve)"
                        className="w-full rounded border px-2 py-1 text-sm"
                      />
                      <p className="text-xs text-gray-400">
                        {(comments[item.id] ?? "").length}/{MAX_COMMENT_LENGTH}
                      </p>
                      {rowErrors[item.id] && (
                        <p role="alert" className="mt-1 text-sm text-red-600">
                          {rowErrors[item.id]}
                        </p>
                      )}
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleApprove(item)}
                          className="rounded bg-green-700 px-3 py-1 text-xs text-white disabled:opacity-50"
                        >
                          {busy ? "Working…" : "Approve"}
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleReject(item)}
                          className="rounded bg-red-700 px-3 py-1 text-xs text-white disabled:opacity-50"
                        >
                          {busy ? "Working…" : "Reject"}
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {queueQuery.data && queueQuery.data.total > 0 && (
          <div className="mt-4 flex items-center gap-3 text-sm">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className="rounded border px-3 py-1 disabled:opacity-50"
            >
              Previous
            </button>
            <span>
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              className="rounded border px-3 py-1 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
