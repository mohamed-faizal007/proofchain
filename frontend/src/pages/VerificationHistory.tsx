import type { ReactElement } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useVerificationsPage } from "../api/hooks/verifications";
import { HashBadge } from "../components/HashBadge";
import { VerdictPill } from "../components/VerdictPill";
import { formatDate } from "../lib/format";

const PAGE_SIZE = 20;

export function VerificationHistory(): ReactElement {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const query = useVerificationsPage(page, PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE_SIZE));

  function setPage(next: number): void {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      params.set("page", String(next));
      return params;
    });
  }

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="text-3xl font-bold tracking-tight">Verification history</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
        Your past verifications, newest first.
      </p>

      <section className="mt-4">
        {query.isLoading ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading verifications…</p>
        ) : query.isError ? (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {query.error instanceof ApiError ? query.error.message : "Something went wrong."}
          </p>
        ) : query.data && query.data.items.length > 0 ? (
          <ul
            // keepPreviousData shows the old page while the next one loads; make that visible
            aria-busy={query.isPlaceholderData}
            className={`divide-y overflow-hidden rounded-xl border bg-white shadow-sm dark:divide-gray-700 dark:border-gray-700 dark:bg-gray-900 ${
              query.isPlaceholderData ? "opacity-60" : ""
            }`}
          >
            {query.data.items.map((v) => (
              <li
                key={v.id}
                className="space-y-1.5 p-4 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <VerdictPill verdict={v.verdict} />
                  <Link
                    to={`/verifications/${v.id}`}
                    className="text-base font-semibold hover:underline"
                  >
                    {v.filename}
                  </Link>
                  <span className="text-gray-500 dark:text-gray-400">{formatDate(v.at)}</span>
                </div>
                <p className="text-gray-700 dark:text-gray-300">{v.summary}</p>
                <p className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  {v.document && <span>Document: {v.document.title ?? v.document.id}</span>}
                  <HashBadge hash={v.file_hash} label="file hash" />
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-600 dark:text-gray-300">
            <p>No verifications yet.</p>
            <Link to="/verify" className="text-blue-600 underline dark:text-blue-400">
              Verify a document
            </Link>
          </div>
        )}

        {query.data && query.data.total > 0 && (
          <div className="mt-4 flex items-center gap-3 text-sm">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className="rounded-lg border bg-white px-4 py-1.5 font-medium shadow-sm hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:hover:bg-gray-800"
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
              className="rounded-lg border bg-white px-4 py-1.5 font-medium shadow-sm hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:hover:bg-gray-800"
            >
              Next
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
