import type { MouseEvent, ReactElement } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useVerificationsPage } from "../api/hooks/verifications";
import { Alert } from "../components/Alert";
import { EmptyState } from "../components/EmptyState";
import { HashBadge } from "../components/HashBadge";
import { RowsSkeleton } from "../components/Skeleton";
import { VerdictPill } from "../components/VerdictPill";
import { formatDate } from "../lib/format";

const PAGE_SIZE = 20;

export function VerificationHistory(): ReactElement {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const query = useVerificationsPage(page, PAGE_SIZE);
  const navigate = useNavigate();

  // Whole-row click is a pointer convenience; the filename link stays the keyboard/AT target.
  function openRow(e: MouseEvent<HTMLElement>, to: string): void {
    if ((e.target as HTMLElement).closest("a,button,input,select,textarea")) return;
    navigate(to);
  }

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
      <h1 className="page-title">Verification history</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
        Your past verifications, newest first.
      </p>

      <section className="mt-4">
        {query.isLoading ? (
          <div className="card">
            <RowsSkeleton label="Loading verifications…" rows={5} />
          </div>
        ) : query.isError ? (
          <Alert>
            {query.error instanceof ApiError ? query.error.message : "Something went wrong."}
          </Alert>
        ) : query.data && query.data.items.length > 0 ? (
          <ul
            // keepPreviousData shows the old page while the next one loads; make that visible
            aria-busy={query.isPlaceholderData}
            className={`stagger card divide-y overflow-hidden transition-opacity duration-200 dark:divide-gray-700/70 ${
              query.isPlaceholderData ? "opacity-60" : ""
            }`}
          >
            {query.data.items.map((v) => (
              <li
                key={v.id}
                onClick={(e) => openRow(e, `/verifications/${v.id}`)}
                className="cursor-pointer space-y-1.5 p-4 text-sm transition-colors hover:bg-blue-50/60 focus-within:bg-blue-50/60 dark:hover:bg-blue-500/10 dark:focus-within:bg-blue-500/10"
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
          <div className="card">
            <EmptyState
              title="No verifications yet"
              action={
                <Link to="/verify" className="btn-primary">
                  Verify a document
                </Link>
              }
            >
              Every document you check is saved here with its verdict and file hash.
            </EmptyState>
          </div>
        )}

        {query.data && query.data.total > 0 && (
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
