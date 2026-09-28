import type { ReactElement } from "react";
import { useState } from "react";
import { useDownloadRevisionFile } from "../api/hooks/revisions";
import { ApiError } from "../api/client";
import type { Revision } from "../api/types";
import { formatDate } from "../lib/format";
import { TxLink } from "./TxLink";

const STATUS_CLASSES: Record<Revision["status"], string> = {
  PENDING: "bg-amber-100 text-amber-800",
  APPROVED: "bg-green-100 text-green-800",
  REJECTED: "bg-red-100 text-red-800",
  REVOKED: "bg-gray-200 text-gray-700",
};

function StatusPill({ status }: { status: Revision["status"] }): ReactElement {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[status]}`}>
      {status}
    </span>
  );
}

export function VersionTimeline({ revisions }: { revisions: Revision[] }): ReactElement {
  const download = useDownloadRevisionFile();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  if (revisions.length === 0) {
    return <p className="text-sm text-gray-500">No revisions yet.</p>;
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

  return (
    <div>
      {downloadError && (
        <p role="alert" className="mb-2 text-sm text-red-600">
          {downloadError}
        </p>
      )}
      <ul className="space-y-3">
        {[...revisions].reverse().map((revision) => (
          <li key={revision.id} className="rounded border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">
                v{revision.revision_no}
                {revision.version_no != null ? ` (on-chain #${revision.version_no})` : ""}
              </span>
              <StatusPill status={revision.status} />
            </div>
            <p className="mt-1 text-gray-500">
              Submitted {formatDate(revision.submitted_at)}
              {revision.change_note ? ` — ${revision.change_note}` : ""}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-gray-500">
              <span>Anchor: {revision.anchor.status}</span>
              <TxLink txHash={revision.anchor.tx_hash} />
            </div>
            {revision.revocation && (
              <p className="mt-1 text-red-600">
                Revoked {formatDate(revision.revocation.at)}: {revision.revocation.reason}
              </p>
            )}
            <button
              type="button"
              onClick={() => void handleDownload(revision)}
              disabled={downloadingId === revision.id}
              className="mt-2 rounded border px-3 py-1 text-xs disabled:opacity-50"
            >
              {downloadingId === revision.id ? "Downloading…" : "Download file"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
