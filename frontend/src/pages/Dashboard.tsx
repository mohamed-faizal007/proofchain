import type { ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocuments } from "../api/hooks/documents";
import { useRecentVerifications } from "../api/hooks/verifications";
import type { DocType, RevisionStatus } from "../api/types";
import { RoleGate } from "../auth/RoleGate";
import { formatDate } from "../lib/format";

const ICON_DOCS = "M7 3h7l5 5v13H7z M14 3v5h5";
const ICON_PENDING = "M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z";
const ICON_SHIELD = "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M9 12l2 2 4-4";

function StatTile({
  icon,
  label,
  children,
}: {
  icon: string;
  label: string;
  children: ReactNode;
}): ReactElement {
  return (
    <div className="card bg-gradient-to-br from-white to-gray-50 p-6 dark:from-gray-800/80 dark:to-gray-900">
      <div className="flex items-center justify-between">
        <p className="eyebrow">{label}</p>
        <span
          aria-hidden="true"
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 ring-1 ring-inset ring-blue-500/25 dark:text-blue-300"
        >
          <svg
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d={icon} />
          </svg>
        </span>
      </div>
      {children}
    </div>
  );
}

const DOC_TYPES: DocType[] = ["CONTRACT", "CERTIFICATE", "INVOICE", "LEGAL", "OTHER"];
const STATUSES: RevisionStatus[] = ["PENDING", "APPROVED", "REJECTED", "REVOKED"];
const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

export function Dashboard(): ReactElement {
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
  const verificationsQuery = useRecentVerifications(5);
  const listQuery = useDocuments({
    q: q || undefined,
    doc_type: docType || undefined,
    status: status || undefined,
    page,
    page_size: PAGE_SIZE,
  });

  const totalPages = listQuery.data ? Math.max(1, Math.ceil(listQuery.data.total / PAGE_SIZE)) : 1;

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-end justify-between">
        <h1 className="page-title">Dashboard</h1>
        <RoleGate roles={["ISSUER"]}>
          <Link to="/documents/new" className="btn-primary">
            New document
          </Link>
        </RoleGate>
      </div>

      <section className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-3">
        <StatTile icon={ICON_DOCS} label="Documents">
          {totalQuery.isLoading ? (
            <p className="mt-4 font-display text-5xl font-bold tabular-nums">…</p>
          ) : totalQuery.isError ? (
            <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
              {errorMessage(totalQuery.error)}
            </p>
          ) : (
            <p className="mt-4 font-display text-5xl font-bold tabular-nums">
              {totalQuery.data?.total ?? 0}
            </p>
          )}
        </StatTile>

        <StatTile icon={ICON_PENDING} label="Pending revision">
          {pendingQuery.isLoading ? (
            <p className="mt-4 font-display text-5xl font-bold tabular-nums">…</p>
          ) : pendingQuery.isError ? (
            <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
              {errorMessage(pendingQuery.error)}
            </p>
          ) : (
            <p className="mt-4 font-display text-5xl font-bold tabular-nums">
              {pendingQuery.data?.total ?? 0}
            </p>
          )}
        </StatTile>

        <StatTile icon={ICON_SHIELD} label="Recent verifications">
          {verificationsQuery.isLoading ? (
            <p className="mt-4 font-display text-5xl font-bold tabular-nums">…</p>
          ) : verificationsQuery.isError ? (
            <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
              {errorMessage(verificationsQuery.error)}
            </p>
          ) : verificationsQuery.data && verificationsQuery.data.items.length > 0 ? (
            <ul className="mt-4 max-h-[6.125rem] space-y-1.5 overflow-y-auto pr-1 text-xs leading-5">
              {verificationsQuery.data.items.map((v) => (
                <li key={v.id}>
                  <Link
                    to={`/verifications/${v.id}`}
                    className="block truncate text-gray-700 hover:text-blue-600 dark:text-gray-200 dark:hover:text-blue-300"
                  >
                    {v.verdict} — {formatDate(v.at)}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">No verifications yet.</p>
          )}
        </StatTile>
      </section>

      <section className="mt-12">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            placeholder="Search by title…"
            aria-label="Search documents"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="px-3 py-2 text-sm"
          />
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

        <div className="card mt-5 overflow-x-auto">
          {listQuery.isLoading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading documents…</p>
          ) : listQuery.isError ? (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {errorMessage(listQuery.error)}
            </p>
          ) : listQuery.data && listQuery.data.items.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No documents match these filters.
            </p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b bg-gray-50 dark:bg-gray-800/40">
                  <th className="eyebrow px-5 py-3.5">Title</th>
                  <th className="eyebrow px-5 py-3.5">Type</th>
                  <th className="eyebrow px-5 py-3.5">Latest version</th>
                  <th className="eyebrow px-5 py-3.5">Revisions</th>
                  <th className="eyebrow px-5 py-3.5">Updated</th>
                </tr>
              </thead>
              <tbody>
                {listQuery.data?.items.map((doc) => (
                  <tr
                    key={doc.id}
                    className="border-b border-gray-100 transition-colors last:border-b-0 hover:bg-blue-50/60 dark:border-gray-800 dark:hover:bg-blue-500/10"
                  >
                    <td className="px-5 py-4">
                      <Link
                        to={`/documents/${doc.id}`}
                        className="font-semibold text-gray-900 hover:text-blue-600 dark:text-white dark:hover:text-blue-300"
                      >
                        {doc.title}
                      </Link>
                    </td>
                    <td className="px-5 py-4">
                      <span className="rounded-md bg-gray-100 px-2 py-0.5 text-xs font-semibold tracking-wide text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                        {doc.doc_type}
                      </span>
                    </td>
                    <td className="px-5 py-4 tabular-nums text-gray-600 dark:text-gray-300">
                      {doc.latest_approved_version_no ?? "—"}
                    </td>
                    <td className="px-5 py-4 tabular-nums text-gray-600 dark:text-gray-300">
                      {doc.revision_count}
                    </td>
                    <td className="px-5 py-4 tabular-nums text-gray-600 dark:text-gray-300">
                      {formatDate(doc.updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
