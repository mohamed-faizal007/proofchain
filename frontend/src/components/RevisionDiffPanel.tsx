import type { ReactElement } from "react";
import { useState } from "react";
import { ApiError } from "../api/client";
import { useRevisionDiff } from "../api/hooks/revisions";
import type { Revision } from "../api/types";
import { candidateHighlights, referenceHighlights } from "../lib/regions";
import { ChangeList } from "./ChangeList";
import LazyPdfViewer from "./LazyPdfViewer";

const label = (r: Revision): string => `v${r.revision_no} · ${r.status}`;

function diffErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return "These revisions use different canonicalization versions, so their hashes can't be compared.";
    }
    return err.message;
  }
  return "Something went wrong.";
}

/** Diff between any two revisions of one document. The API allows any revision status as either
 * side (04_API_SPEC: approvers review PENDING ones here), so nothing is filtered out; the status
 * is shown in the option label instead. Unlike a verification report there is no verdict, step
 * list or chain check, only the localization and (optional) analysis. */
export function RevisionDiffPanel({ revisions }: { revisions: Revision[] }): ReactElement {
  const sorted = [...revisions].sort((a, b) => a.revision_no - b.revision_no);
  const latest = sorted.at(-1);
  const [candidateId, setCandidateId] = useState<string | undefined>(latest?.id);
  const [againstId, setAgainstId] = useState("");
  const [selectedId, setSelectedId] = useState<string | undefined>();

  const candidate = sorted.find((r) => r.id === candidateId) ?? latest;
  const needsReference = candidate != null && candidate.parent_revision_id == null && !againstId;
  const canDiff = sorted.length >= 2 && candidate != null && !needsReference;
  const diffQuery = useRevisionDiff(candidate?.id, againstId || undefined, { enabled: canDiff });

  if (sorted.length < 2 || !candidate) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        A diff needs at least two revisions; this document has {sorted.length}.
      </p>
    );
  }

  const selectClass = "rounded border px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800";
  const diff = diffQuery.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex flex-col gap-1">
          Candidate (newer)
          <select
            className={selectClass}
            value={candidate.id}
            onChange={(e) => {
              setCandidateId(e.target.value);
              setAgainstId("");
              setSelectedId(undefined);
            }}
          >
            {sorted.map((r) => (
              <option key={r.id} value={r.id}>
                {label(r)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Reference (older)
          <select
            className={selectClass}
            value={againstId}
            onChange={(e) => {
              setAgainstId(e.target.value);
              setSelectedId(undefined);
            }}
          >
            <option value="">Parent (default)</option>
            {sorted
              .filter((r) => r.id !== candidate.id)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {label(r)}
                </option>
              ))}
          </select>
        </label>
      </div>

      {needsReference ? (
        <p className="text-sm text-gray-600 dark:text-gray-300">
          This revision has no parent, so choose a reference revision to compare against.
        </p>
      ) : diffQuery.isLoading ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Comparing revisions…</p>
      ) : diffQuery.isError ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {diffErrorMessage(diffQuery.error)}
        </p>
      ) : diff ? (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="min-w-0 space-y-1">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">Reference</h4>
              <LazyPdfViewer
                revisionId={diff.against_revision_id}
                highlights={referenceHighlights(diff.localization.regions)}
                focusedId={selectedId}
              />
            </div>
            <div className="min-w-0 space-y-1">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">Candidate</h4>
              <LazyPdfViewer
                revisionId={diff.revision_id}
                highlights={candidateHighlights(diff.localization.regions)}
                focusedId={selectedId}
              />
            </div>
          </div>
          <section aria-label="Changes" className="space-y-2">
            <h3 className="font-semibold">Changes</h3>
            {diff.localization.status === "IDENTICAL" ? (
              <p className="text-sm text-gray-600 dark:text-gray-300">
                These revisions are identical.
              </p>
            ) : (
              <>
                {diff.localization.status === "CONTENT_EQUIVALENT" && (
                  <p className="text-sm text-gray-600 dark:text-gray-300">
                    The text is equivalent after normalization; only formatting differs.
                  </p>
                )}
                <ChangeList
                  regions={diff.localization.regions}
                  analysis={diff.analysis}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              </>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
