import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocuments } from "../api/hooks/documents";
import { useRecentVerifications } from "../api/hooks/verifications";
import type { DocType, RevisionStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { RoleGate } from "../auth/RoleGate";
import { Alert } from "../components/Alert";
import { ChainStatusCard } from "../components/dashboard/ChainStatusCard";
import { DashboardHero } from "../components/dashboard/DashboardHero";
import { DocumentsTable } from "../components/dashboard/DocumentsTable";
import { RECENT_COUNT, RecentVerifications } from "../components/dashboard/RecentVerifications";
import { StatTile, StatValue } from "../components/dashboard/StatTile";
import { EmptyState } from "../components/EmptyState";
import { Icon } from "../components/icons";
import { LoadingRegion, RowsSkeleton, Skeleton } from "../components/Skeleton";
import { verdictInfo } from "../lib/verdict";

const DOC_TYPES: DocType[] = ["CONTRACT", "CERTIFICATE", "INVOICE", "LEGAL", "OTHER"];
const STATUSES: RevisionStatus[] = ["PENDING", "APPROVED", "REJECTED", "REVOKED"];
const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

export function Dashboard(): ReactElement {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const docType = (searchParams.get("doc_type") as DocType | null) ?? "";
  const status = (searchParams.get("status") as RevisionStatus | null) ?? "";
  const page = Math.max(1, Number(searchParams.get("page")) || 1);

  // Local input state decoupled from the URL so keystrokes don't refetch on every character.
  const [searchInput, setSearchInput] = useState(q);
  useEffect(() => setSearchInput(q), [q]);

  useEffect(() => {
    if (searchInput === q) return;
    const handle = setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (searchInput) next.set("q", searchInput);
        else next.delete("q");
        next.set("page", "1");
        return next;
      });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [searchInput, q, setSearchParams]);

  function setFilter(key: "doc_type" | "status", value: string): void {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      next.set("page", "1");
      return next;
    });
  }

  function setPage(next: number): void {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      params.set("page", String(next));
      return params;
    });
  }

  const totalQuery = useDocuments({ page: 1, page_size: 1 });
  const pendingQuery = useDocuments({ page: 1, page_size: 1, status: "PENDING" });
  const approvedQuery = useDocuments({ page: 1, page_size: 1, status: "APPROVED" });
  const verificationsQuery = useRecentVerifications(RECENT_COUNT);
  const listQuery = useDocuments({
    q: q || undefined,
    doc_type: docType || undefined,
    status: status || undefined,
    page,
    page_size: PAGE_SIZE,
  });

  const filtered = !!(q || docType || status);
  const totalPages = listQuery.data ? Math.max(1, Math.ceil(listQuery.data.total / PAGE_SIZE)) : 1;

  const total = totalQuery.data?.total ?? 0;
  const pending = pendingQuery.data?.total ?? 0;
  const recent = verificationsQuery.data?.items ?? [];
  const tones = recent.map((v) => verdictInfo(v.verdict).tone);
  const authentic = tones.filter((t) => t === "green").length;
  const flagged = tones.filter((t) => t === "red").length;

  return (
    <main className="mx-auto max-w-[88rem] space-y-8 px-4 py-8 sm:px-6">
      {user ? (
        <DashboardHero
          user={user}
          summary={
            totalQuery.isSuccess && pendingQuery.isSuccess
              ? `${total} ${total === 1 ? "document" : "documents"} tracked, ${pending} awaiting approval.`
              : "Everything ProofChain is tracking for you, at a glance."
          }
        />
      ) : null}
      {/* The hero carries the visible greeting; this keeps one stable page heading. */}
      <h1 className="sr-only">Dashboard</h1>

      <section
        aria-label="Key figures"
        className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3"
      >
        <StatTile
          icon="document"
          label="Documents"
          hint={
            approvedQuery.isSuccess
              ? `${approvedQuery.data.total} with an approved version`
              : "Registered documents across all issuers"
          }
        >
          {totalQuery.isLoading ? (
            <LoadingRegion label="Loading document count…">
              <Skeleton className="h-10 w-20" />
            </LoadingRegion>
          ) : totalQuery.isError ? (
            <Alert>{errorMessage(totalQuery.error)}</Alert>
          ) : (
            <StatValue>{total}</StatValue>
          )}
        </StatTile>

        <StatTile
          icon="clock"
          label="Pending revision"
          tone="amber"
          hint={pending > 0 ? "Waiting for an approver to review" : "Nothing is waiting for review"}
        >
          {pendingQuery.isLoading ? (
            <LoadingRegion label="Loading pending count…">
              <Skeleton className="h-10 w-20" />
            </LoadingRegion>
          ) : pendingQuery.isError ? (
            <Alert>{errorMessage(pendingQuery.error)}</Alert>
          ) : (
            <StatValue>{pending}</StatValue>
          )}
        </StatTile>

        <StatTile
          icon="shield"
          label="Verifications"
          tone="accent"
          hint={
            recent.length > 0
              ? `${authentic} authentic, ${flagged} flagged in the latest ${recent.length}`
              : "Your checks will be counted here"
          }
        >
          {verificationsQuery.isLoading ? (
            <LoadingRegion label="Loading recent verifications…">
              <Skeleton className="h-10 w-20" />
            </LoadingRegion>
          ) : verificationsQuery.isError ? (
            <Alert>{errorMessage(verificationsQuery.error)}</Alert>
          ) : (
            <StatValue>{verificationsQuery.data?.total ?? 0}</StatValue>
          )}
        </StatTile>
      </section>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RecentVerifications />
        </div>
        <ChainStatusCard />
      </div>

      <section aria-label="Documents">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="section-title">Documents</h2>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Icon
                name="search"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              />
              <input
                type="search"
                placeholder="Search by title…"
                aria-label="Search documents"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-56 py-2 pl-9 pr-3 text-sm"
              />
            </div>
            <select
              aria-label="Filter by document type"
              value={docType}
              onChange={(e) => setFilter("doc_type", e.target.value)}
              className="px-3 py-2 text-sm"
            >
              <option value="">All types</option>
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by status"
              value={status}
              onChange={(e) => setFilter("status", e.target.value)}
              className="px-3 py-2 text-sm"
            >
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="card scroll-thin mt-4 overflow-x-auto">
          {listQuery.isLoading ? (
            <RowsSkeleton label="Loading documents…" rows={5} />
          ) : listQuery.isError ? (
            <Alert className="m-4">{errorMessage(listQuery.error)}</Alert>
          ) : listQuery.data && listQuery.data.items.length === 0 ? (
            filtered ? (
              <EmptyState
                title="No documents match these filters"
                action={
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setSearchInput("");
                      setSearchParams({});
                    }}
                  >
                    Clear filters
                  </button>
                }
              >
                Try a different search term, type or status.
              </EmptyState>
            ) : (
              <EmptyState
                title="No documents yet"
                action={
                  <RoleGate roles={["ISSUER"]}>
                    <Link to="/documents/new" className="btn-primary">
                      New document
                    </Link>
                  </RoleGate>
                }
              >
                Register a PDF to anchor its fingerprint on the blockchain and start tracking
                revisions.
              </EmptyState>
            )
          ) : (
            <DocumentsTable items={listQuery.data?.items ?? []} />
          )}
        </div>

        {listQuery.data && listQuery.data.total > 0 && (
          <div className="mt-5 flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className="btn-secondary"
            >
              Previous
            </button>
            <span className="num">
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
