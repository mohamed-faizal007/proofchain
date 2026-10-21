import type { ReactElement } from "react";
import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApproveRevision, usePendingRevisions, useRejectRevision } from "../api/hooks/revisions";
import { ApiError } from "../api/client";
import type { PendingRevision } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Alert } from "../components/Alert";
import { EmptyState } from "../components/EmptyState";
import { CardsSkeleton } from "../components/Skeleton";
import { IconTile, StatusBadge, VersionBadge } from "../components/Badges";
import { Icon } from "../components/icons";
import { PageHeader } from "../components/PageHeader";
import { Spinner } from "../components/Spinner";
import { formatDate, relativeTime } from "../lib/format";

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
  const [busyAction, setBusyAction] = useState<"approve" | "reject" | null>(null);
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
    setBusyAction("approve");
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
      setBusyAction(null);
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
    setBusyAction("reject");
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
      setBusyAction(null);
    }
  }

  if (!isApprover) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        <PageHeader icon="inbox" title="Approvals">
          This page requires the APPROVER role. ADMIN accounts can manage anchoring and user roles
          but are not approvers, so they cannot review revisions here.
        </PageHeader>
      </main>
    );
  }

  const totalPages = queueQuery.data
    ? Math.max(1, Math.ceil(queueQuery.data.total / PAGE_SIZE))
    : 1;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <PageHeader
        icon="inbox"
        title="Approvals"
        actions={
          queueQuery.data ? (
            <span className="badge badge-amber !px-3 !py-1 !text-sm">
              <span className="num">{queueQuery.data.total}</span> pending
            </span>
          ) : undefined
        }
      >
        Pending revisions across all documents, oldest first. You cannot review a revision you
        submitted yourself.
      </PageHeader>

      {statusMessage && (
        <Alert variant="success" className="mt-4">
          {statusMessage}
        </Alert>
      )}

      <section className="mt-6">
        {queueQuery.isLoading ? (
          <CardsSkeleton label="Loading approvals…" count={3} />
        ) : queueQuery.isError ? (
          <Alert>{errorMessage(queueQuery.error)}</Alert>
        ) : queueQuery.data && queueQuery.data.items.length === 0 ? (
          <div className="card">
            <EmptyState title="No pending revisions.">
              You&apos;re all caught up. New revisions submitted by issuers will queue up here.
            </EmptyState>
          </div>
        ) : (
          <ul className="stagger space-y-5">
            {queueQuery.data?.items.map((item) => {
              const ownSubmission = user?.id === item.submitted_by;
              const busy = busyId === item.id;
              return (
                <li key={item.id} className="card overflow-hidden text-sm">
                  <div className="h-1 bg-gradient-to-r from-amber-300 to-orange-500" />
                  <div className="p-5 sm:p-6">
                    <div className="flex items-start gap-4">
                      <IconTile name="document" className="h-11 w-11" />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link
                            to={`/documents/${item.document_id}`}
                            className="font-display text-lg font-bold tracking-tight hover:text-blue-600 dark:hover:text-blue-300"
                          >
                            {item.document_title ?? "Untitled document"}
                          </Link>
                          <VersionBadge>{`v${item.revision_no}`}</VersionBadge>
                          <StatusBadge status="PENDING" />
                        </div>
                        <p className="mt-1 text-gray-500 dark:text-gray-400">
                          <time dateTime={item.submitted_at} title={formatDate(item.submitted_at)}>
                            Submitted {relativeTime(item.submitted_at)}
                          </time>{" "}
                          by <span className="font-mono text-xs">{item.submitted_by}</span>
                        </p>
                        {item.change_note && (
                          <p className="mt-3 rounded-xl bg-gray-50 px-3.5 py-2.5 text-gray-700 dark:bg-gray-800/60 dark:text-gray-200">
                            <span className="eyebrow mr-2 !text-[10px]">Note</span>
                            {item.change_note}
                          </p>
                        )}
                      </div>
                    </div>

                    {ownSubmission ? (
                      <p className="mt-4 flex items-center gap-2 rounded-xl bg-blue-500/10 px-3.5 py-2.5 text-blue-900 dark:text-blue-100">
                        <Icon name="lock" className="h-4 w-4 shrink-0" />
                        You submitted this revision; another APPROVER must review it.
                      </p>
                    ) : (
                      <div className="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
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
                          className="w-full px-3 py-2 text-sm"
                        />
                        <p className="num mt-1 text-xs text-gray-400">
                          {(comments[item.id] ?? "").length}/{MAX_COMMENT_LENGTH}
                        </p>
                        {rowErrors[item.id] && <Alert className="mt-2">{rowErrors[item.id]}</Alert>}
                        <div className="mt-3 flex flex-wrap gap-3">
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void handleApprove(item)}
                            className="btn-primary px-5"
                          >
                            {busy && busyAction === "approve" ? (
                              <Spinner />
                            ) : (
                              <Icon name="check" className="h-4 w-4" strokeWidth={2.4} />
                            )}
                            {busy ? "Working…" : "Approve"}
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void handleReject(item)}
                            className="btn-danger"
                          >
                            {busy && busyAction === "reject" ? (
                              <Spinner />
                            ) : (
                              <Icon name="x" className="h-4 w-4" strokeWidth={2.4} />
                            )}
                            {busy ? "Working…" : "Reject"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
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
              className="btn-secondary"
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
              className="btn-secondary"
            >
              Next
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
