import type { ReactElement } from "react";
import { useState } from "react";
import { useDownloadRevisionFile } from "../api/hooks/revisions";
import { ApiError } from "../api/client";
import type { Revision, RevisionStatus } from "../api/types";
import { formatDate, relativeTime } from "../lib/format";
import { Alert } from "./Alert";
import { AnchorBadge, StatusBadge, VersionBadge } from "./Badges";
import { EmptyState } from "./EmptyState";
import { Icon, type IconName } from "./icons";
import { RevisionActions } from "./RevisionActions";
import { Spinner } from "./Spinner";
import { TxLink } from "./TxLink";

const NODE: Record<RevisionStatus, { icon: IconName; cls: string }> = {
  PENDING: {
    icon: "clock",
    cls: "bg-amber-500/15 text-amber-600 ring-amber-500/40 dark:text-amber-300",
  },
  APPROVED: {
    icon: "check",
    cls: "bg-green-500/15 text-green-600 ring-green-500/40 dark:text-green-300",
  },
  REJECTED: { icon: "x", cls: "bg-red-500/15 text-red-600 ring-red-500/40 dark:text-red-300" },
  REVOKED: {
    icon: "x",
    cls: "bg-gray-500/15 text-gray-500 ring-gray-500/40 dark:text-gray-300",
  },
};

export function VersionTimeline({ revisions }: { revisions: Revision[] }): ReactElement {
  const download = useDownloadRevisionFile();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  if (revisions.length === 0) {
    return (
      <div className="card">
        <EmptyState title="No revisions yet">
          The first revision appears here once a PDF has been uploaded.
        </EmptyState>
      </div>
    );
  }

  async function handleDownload(revision: Revision): Promise<void> {
    setDownloadingId(revision.id);
    setDownloadError(null);
    try {
      await download.mutateAsync({
        revisionId: revision.id,
        filename: revision.original_filename,
      });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Download failed.";
      setDownloadError(`Could not download revision ${revision.revision_no}: ${message}`);
    } finally {
      setDownloadingId(null);
    }
  }

  const newestFirst = [...revisions].reverse();
  return (
    <div>
      {downloadError && <Alert className="mb-3">{downloadError}</Alert>}
      <ol className="stagger">
        {newestFirst.map((revision, i) => {
          const node = NODE[revision.status];
          const last = i === newestFirst.length - 1;
          return (
            <li key={revision.id} className="relative flex gap-4 pb-5 last:pb-0">
              {!last && (
                <span
                  aria-hidden="true"
                  className="absolute bottom-0 left-[1.1rem] top-10 w-px bg-gradient-to-b from-gray-300 to-gray-200 dark:from-gray-600 dark:to-gray-800"
                />
              )}
              <span
                aria-hidden="true"
                className={`relative z-[1] flex h-9 w-9 shrink-0 items-center justify-center rounded-full ring-2 ${node.cls}`}
              >
                <Icon name={node.icon} className="h-4 w-4" strokeWidth={2.4} />
              </span>
              <div className="card min-w-0 flex-1 p-4 text-sm sm:p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <VersionBadge>{`v${revision.revision_no}`}</VersionBadge>
                  {revision.version_no != null && (
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      on-chain #{revision.version_no}
                    </span>
                  )}
                  <span className="ml-auto flex flex-wrap items-center gap-2">
                    <StatusBadge status={revision.status} />
                    <AnchorBadge status={revision.anchor.status} />
                  </span>
                </div>

                <p className="mt-3 text-gray-700 dark:text-gray-200">
                  {revision.change_note || (
                    <span className="text-gray-400 dark:text-gray-500">No change note.</span>
                  )}
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  <time dateTime={revision.submitted_at} title={formatDate(revision.submitted_at)}>
                    Submitted {relativeTime(revision.submitted_at)}
                  </time>
                  {" · "}
                  <span title={revision.original_filename}>{revision.original_filename}</span>
                </p>

                {revision.anchor.tx_hash || revision.anchor.status === "ANCHORED" ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    <span>Transaction</span>
                    <TxLink txHash={revision.anchor.tx_hash} />
                    {revision.anchor.block_number != null && (
                      <span className="num">block #{revision.anchor.block_number}</span>
                    )}
                  </div>
                ) : null}

                {revision.revocation && (
                  <p className="mt-3 flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-red-700 dark:text-red-300">
                    <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      Revoked {formatDate(revision.revocation.at)}: {revision.revocation.reason}
                    </span>
                  </p>
                )}

                <div className="mt-4 flex flex-wrap items-start gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
                  <button
                    type="button"
                    onClick={() => void handleDownload(revision)}
                    disabled={downloadingId === revision.id}
                    className="btn-secondary text-xs"
                  >
                    {downloadingId === revision.id ? (
                      <Spinner />
                    ) : (
                      <Icon name="download" className="h-3.5 w-3.5" />
                    )}
                    {downloadingId === revision.id ? "Downloading…" : "Download file"}
                  </button>
                  <div className="min-w-0 flex-1 basis-full empty:hidden sm:basis-0 sm:[&>div]:mt-0">
                    <RevisionActions revision={revision} />
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
