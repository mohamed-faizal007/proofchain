import type { ReactElement } from "react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { VerificationReport } from "../api/types";
import { candidateHighlights, referenceHighlights } from "../lib/regions";
import { ChainProofPanel } from "./ChainProofPanel";
import { ChangeList } from "./ChangeList";
import { HashBadge } from "./HashBadge";
import LazyPdfViewer from "./LazyPdfViewer";
import { PipelineSteps } from "./PipelineSteps";
import { IconTile } from "./Badges";
import { VerdictBanner, type VerdictFact } from "./VerdictBanner";

const PANEL = "card p-5 sm:p-6";
const PANEL_TITLE = "eyebrow";
const PANE_LABEL =
  "text-xs font-semibold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400";

export const CANDIDATE_NOT_STORED_MESSAGE =
  "The uploaded file isn't stored -- this view shows the reference document and the detected changes, but not the original upload.";

const NO_REFERENCE_TEXT: Record<string, string> = {
  NO_APPROVED_REVISION: "this document has no approved revision yet",
  CANON_VERSION_MISMATCH: "its approved revisions use a different canonicalization version",
};

export interface VerificationReportViewProps {
  report: VerificationReport;
  /** The uploaded PDF, only available in the session that ran the check (it is never stored). */
  candidateFile?: File;
  /** Anonymous callers get a redacted report and may not download revisions (ADR-021). */
  isAnonymous: boolean;
}

function PaneMessage({ testId, children }: { testId: string; children: string }): ReactElement {
  return (
    <p
      data-testid={testId}
      className="rounded-xl border border-dashed p-8 text-center text-sm text-gray-600 dark:text-gray-300"
    >
      {children}
    </p>
  );
}

/** The full report: banner, pipeline, side-by-side viewers, change list, chain proof. Used for
 * both a fresh /verify result (with the in-memory upload) and a stored /verifications/:id. */
export function VerificationReportView({
  report,
  candidateFile,
  isAnonymous,
}: VerificationReportViewProps): ReactElement {
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const regions = report.localization?.regions ?? [];
  // An exact match has no separate reference; show the matched revision so the pane is not empty.
  const reference = report.reference_revision ?? report.matched_revision;

  let referencePane: ReactElement;
  if (isAnonymous) {
    // Distinct from "no reference": a reference may exist, but anonymous callers cannot fetch it.
    referencePane = (
      <PaneMessage testId="reference-hidden-anonymous">
        Sign in to view the reference document.
      </PaneMessage>
    );
  } else if (!reference) {
    const why = report.no_reference_reason ? NO_REFERENCE_TEXT[report.no_reference_reason] : null;
    referencePane = (
      <PaneMessage testId="reference-hidden-no-reference">
        {`No reference document was available for comparison${why ? `: ${why}` : ""}.`}
      </PaneMessage>
    );
  } else {
    referencePane = (
      <LazyPdfViewer
        revisionId={reference.id}
        highlights={referenceHighlights(regions)}
        focusedId={selectedId}
      />
    );
  }

  const checkedAgainst = report.matched_revision ?? reference;
  const facts: VerdictFact[] = [
    { label: "Document", value: report.document?.title ?? report.document?.id ?? "Not matched" },
    { label: "Uploaded file", value: report.candidate.filename ?? "Unnamed file" },
    { label: "Pages", value: String(report.candidate.page_count) },
    {
      label: "Checked against",
      value: checkedAgainst
        ? `Revision ${checkedAgainst.revision_no}${checkedAgainst.version_no != null ? ` (on-chain #${checkedAgainst.version_no})` : ""}`
        : "No reference",
    },
  ];

  return (
    <div className="space-y-6">
      <VerdictBanner verdict={report.verdict} summary={report.summary} facts={facts} />

      {!candidateFile && !bannerDismissed && (
        <div
          role="note"
          data-testid="candidate-not-stored"
          className="flex items-start justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50 p-3.5 text-sm text-blue-900 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-100"
        >
          <p>{CANDIDATE_NOT_STORED_MESSAGE}</p>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => setBannerDismissed(true)}
            className="font-semibold"
          >
            �
          </button>
        </div>
      )}

      <section aria-label="Pipeline" className={`${PANEL}`}>
        <h3 className={`${PANEL_TITLE} mb-5`}>Pipeline</h3>
        <PipelineSteps steps={report.steps} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label="Details" className={`${PANEL} space-y-3 text-sm`}>
          <h3 className={PANEL_TITLE}>Uploaded file</h3>
          <div className="flex items-center gap-3">
            <IconTile name="file" className="h-11 w-11" />
            <div className="min-w-0">
              {report.candidate.filename && (
                <p className="truncate text-base font-semibold">{report.candidate.filename}</p>
              )}
              <p className="text-gray-600 dark:text-gray-300">
                <span className="num">{report.candidate.page_count}</span> pages
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <HashBadge hash={report.candidate.file_hash} label="file hash" />
            <HashBadge hash={report.candidate.text_root} label="text root" />
          </div>
          {report.document && (
            <p className="text-gray-600 dark:text-gray-300">
              Document:{" "}
              {isAnonymous ? (
                (report.document.title ?? report.document.id)
              ) : (
                <Link to={`/documents/${report.document.id}`} className="link">
                  {report.document.title ?? report.document.id}
                </Link>
              )}
            </p>
          )}
        </section>
        <ChainProofPanel check={report.chain_check} revision={checkedAgainst} />
      </div>

      <section aria-label="Documents" className={`${PANEL} space-y-3`}>
        <h3 className={PANEL_TITLE}>Documents</h3>
        <div className={`grid gap-4 ${candidateFile ? "lg:grid-cols-2" : ""}`}>
          <div data-testid="viewer-reference" className="min-w-0 space-y-1.5">
            <h4 className={PANE_LABEL}>Reference</h4>
            {referencePane}
          </div>
          {candidateFile && (
            <div data-testid="viewer-candidate" className="min-w-0 space-y-1.5">
              <h4 className={PANE_LABEL}>Uploaded</h4>
              {isAnonymous && (
                <p className="text-xs text-gray-600 dark:text-gray-300">
                  Change locations are not included in the public report.
                </p>
              )}
              <LazyPdfViewer
                file={candidateFile}
                highlights={candidateHighlights(regions)}
                focusedId={selectedId}
              />
            </div>
          )}
        </div>
      </section>

      <section aria-label="Changes" className={`${PANEL} space-y-4`}>
        <h3 className={PANEL_TITLE}>Changes</h3>
        {report.localization ? (
          <ChangeList
            regions={regions}
            analysis={report.analysis}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        ) : (
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Nothing was compared, so there are no changes to list.
          </p>
        )}
      </section>
    </div>
  );
}
