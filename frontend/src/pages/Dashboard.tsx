import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocuments } from "../api/hooks/documents";
import { useRecentVerifications } from "../api/hooks/verifications";
import type { DocType, RevisionStatus } from "../api/types";
import { RoleGate } from "../auth/RoleGate";
import { formatDate } from "../lib/format";

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
    <main className="p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <RoleGate roles={["ISSUER"]}>
          <Link to="/documents/new" className="rounded bg-gray-900 px-4 py-2 text-sm text-white">
            New document
          </Link>
        </RoleGate>
      </div>

      <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Documents</p>
          {totalQuery.isLoading ? (
            <p className="mt-1 text-2xl font-semibold">…</p>
          ) : totalQuery.isError ? (
            <p role="alert" className="mt-1 text-sm text-red-600">
              {errorMessage(totalQuery.error)}
            </p>
          ) : (
            <p className="mt-1 text-2xl font-semibold">{totalQuery.data?.total ?? 0}</p>
          )}
        </div>

        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Documents with a pending revision</p>
          {pendingQuery.isLoading ? (
            <p className="mt-1 text-2xl font-semibold">…</p>
          ) : pendingQuery.isError ? (
            <p role="alert" className="mt-1 text-sm text-red-600">
              {errorMessage(pendingQuery.error)}
            </p>
          ) : (
            <p className="mt-1 text-2xl font-semibold">{pendingQuery.data?.total ?? 0}</p>
          )}
        </div>

        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Your recent verifications</p>
          {verificationsQuery.isLoading ? (
            <p className="mt-1 text-2xl font-semibold">…</p>
          ) : verificationsQuery.isError ? (
            <p role="alert" className="mt-1 text-sm text-red-600">
              {errorMessage(verificationsQuery.error)}
            </p>
          ) : verificationsQuery.data && verificationsQuery.data.items.length > 0 ? (
            <ul className="mt-1 space-y-1 text-sm">
              {verificationsQuery.data.items.map((v) => (
                <li key={v.id}>
                  <Link to={`/verifications/${v.id}`} className="hover:underline">
                    {v.verdict} — {formatDate(v.at)}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-sm text-gray-500">No verifications yet.</p>
          )}
        </div>
      </section>

      <section className="mt-8">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            placeholder="Search by title…"
            aria-label="Search documents"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="rounded border px-3 py-2 text-sm"
          />
          <select
            aria-label="Filter by document type"
            value={docType}
            onChange={(e) => setFilter("doc_type", e.target.value)}
            className="rounded border px-3 py-2 text-sm"
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
            className="rounded border px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4 overflow-x-auto">
          {listQuery.isLoading ? (
            <p className="text-sm text-gray-500">Loading documents…</p>
          ) : listQuery.isError ? (
            <p role="alert" className="text-sm text-red-600">
              {errorMessage(listQuery.error)}
            </p>
          ) : listQuery.data && listQuery.data.items.length === 0 ? (
            <p className="text-sm text-gray-500">No documents match these filters.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b text-gray-500">
                  <th className="py-2 pr-4">Title</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Latest version</th>
                  <th className="py-2 pr-4">Revisions</th>
                  <th className="py-2 pr-4">Updated</th>
                </tr>
              </thead>
              <tbody>
                {listQuery.data?.items.map((doc) => (
                  <tr key={doc.id} className="border-b">
                    <td className="py-2 pr-4">
                      <Link to={`/documents/${doc.id}`} className="hover:underline">
                        {doc.title}
                      </Link>
                    </td>
                    <td className="py-2 pr-4">{doc.doc_type}</td>
                    <td className="py-2 pr-4">{doc.latest_approved_version_no ?? "—"}</td>
                    <td className="py-2 pr-4">{doc.revision_count}</td>
                    <td className="py-2 pr-4">{formatDate(doc.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {listQuery.data && listQuery.data.total > 0 && (
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
