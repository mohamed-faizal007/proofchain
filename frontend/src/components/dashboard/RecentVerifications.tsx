import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import { useRecentVerifications } from "../../api/hooks/verifications";
import { ApiError } from "../../api/client";
import { formatDate, relativeTime } from "../../lib/format";
import { Alert } from "../Alert";
import { EmptyState } from "../EmptyState";
import { Icon } from "../icons";
import { RowsSkeleton } from "../Skeleton";
import { VerdictPill } from "../VerdictPill";

export const RECENT_COUNT = 8;

/** Latest verifications as a scrollable list: verdict, file, when, and a link to the report. */
export function RecentVerifications(): ReactElement {
  const query = useRecentVerifications(RECENT_COUNT);
  return (
    <section aria-label="Recent verifications" className="card flex flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-5 pb-3 pt-5">
        <h2 className="section-title !text-base">Recent verifications</h2>
        <Link to="/verifications" className="link inline-flex items-center gap-1 text-sm">
          View all
          <Icon name="arrowRight" className="h-3.5 w-3.5" />
        </Link>
      </div>
      {query.isLoading ? (
        <RowsSkeleton label="Loading recent verifications…" rows={4} />
      ) : query.isError ? (
        <Alert className="m-5 mt-0">
          {query.error instanceof ApiError ? query.error.message : "Something went wrong."}
        </Alert>
      ) : query.data && query.data.items.length > 0 ? (
        <ul className="scroll-thin stagger max-h-[21rem] divide-y divide-gray-100 overflow-y-auto border-t border-gray-100 dark:divide-gray-800 dark:border-gray-800">
          {query.data.items.map((v) => (
            <li
              key={v.id}
              className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-5 py-3 transition-colors hover:bg-blue-50/60 dark:hover:bg-blue-500/5"
            >
              <VerdictPill verdict={v.verdict} />
              <div className="min-w-0 flex-1 basis-40">
                <p className="truncate text-sm font-medium">{v.filename}</p>
                {v.document?.title && (
                  <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                    {v.document.title}
                  </p>
                )}
              </div>
              <time
                dateTime={v.at}
                title={formatDate(v.at)}
                className="text-xs text-gray-500 dark:text-gray-400"
              >
                {relativeTime(v.at)}
              </time>
              <Link
                to={`/verifications/${v.id}`}
                aria-label={`View report for ${v.filename}`}
                className="link inline-flex items-center gap-1 text-xs"
              >
                Report
                <Icon name="arrowRight" className="h-3 w-3" />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="No verifications yet"
          action={
            <Link to="/verify" className="link">
              Verify a document
            </Link>
          }
        >
          Check a PDF against the approved versions and the result is saved here.
        </EmptyState>
      )}
    </section>
  );
}
