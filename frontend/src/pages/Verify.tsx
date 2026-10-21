import type { FormEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocuments } from "../api/hooks/documents";
import { useVerify } from "../api/hooks/verifications";
import type { VerificationReport } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Alert } from "../components/Alert";
import { IconTile } from "../components/Badges";
import { Collapse } from "../components/Collapse";
import { FileDropzone } from "../components/FileDropzone";
import { Icon, type IconName } from "../components/icons";
import { Spinner } from "../components/Spinner";
import { VerificationReportView } from "../components/VerificationReportView";
import { validatePdfFile } from "../lib/pdfFile";

const HOW_IT_WORKS: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "fingerprint",
    title: "Fingerprint",
    body: "The PDF is hashed and its text is split into a Merkle tree.",
  },
  {
    icon: "layers",
    title: "Compare",
    body: "The fingerprint is matched to approved versions; any difference is located.",
  },
  {
    icon: "link",
    title: "Confirm on-chain",
    body: "The matching record is checked against the blockchain registry.",
  },
];

function mapVerifyError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case "FILE_TOO_LARGE":
        return "The file is too large for the server to accept.";
      case "INVALID_PDF":
        return "That file is not a valid PDF.";
      case "ENCRYPTED_PDF":
        return "Encrypted PDFs are not supported.";
      case "NO_EXTRACTABLE_TEXT":
        return "No extractable text was found in this PDF (scanned/image-only PDFs are not supported).";
      default:
        return err.status === 401 ? "Sign in to verify documents." : err.message;
    }
  }
  return "Verification failed. Please try again.";
}

/** Upload bar, then an indeterminate "analysing" bar once the bytes are sent: the server hashes,
 * extracts, compares and (optionally) explains, which can take several seconds. */
function UploadProgress({ progress }: { progress: number | null }): ReactElement {
  const uploading = progress === null || progress < 1;
  const pct = Math.round((progress ?? 0) * 100);
  return (
    <div role="status" className="space-y-1.5 text-sm text-gray-600 dark:text-gray-300">
      <p>
        {uploading ? `Uploading… ${pct}%` : "Analysing the document… this can take a few seconds."}
      </p>
      <div
        role="progressbar"
        aria-label="Verification progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={uploading ? pct : undefined}
        className="h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800"
      >
        <div
          className={`h-full rounded-full bg-blue-500 ${uploading ? "transition-[width] duration-200" : "progress-indeterminate"}`}
          style={uploading ? { width: `${pct}%` } : undefined}
        />
      </div>
    </div>
  );
}

/** Public page (PUBLIC_VERIFY). The result renders inline and keeps the uploaded File in memory,
 * because the server never stores the candidate; that is what feeds the candidate viewer. */
export function Verify(): ReactElement {
  const { user } = useAuth();
  const verify = useVerify();
  // Anonymous callers must not hit /documents: its 401 would sign them out and redirect to /login.
  const documents = useDocuments({ page: 1, page_size: 100 }, { enabled: user !== null });
  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [includeNlp, setIncludeNlp] = useState(true);
  const [fileError, setFileError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<{ report: VerificationReport; file: File } | null>(null);
  const submittingRef = useRef(false);
  // 0..1 while the file uploads; `null` before the first progress event.
  const [progress, setProgress] = useState<number | null>(null);

  async function runVerify(upload: File, againstDocumentId: string): Promise<void> {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setFormError(null);
    setProgress(null);
    try {
      const report = await verify.mutateAsync({
        file: upload,
        documentId: againstDocumentId || undefined,
        includeNlp,
        onUploadProgress: setProgress,
      });
      setResult({ report, file: upload });
    } catch (err) {
      setFormError(mapVerifyError(err));
    } finally {
      submittingRef.current = false;
    }
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    const invalid = validatePdfFile(file);
    setFileError(invalid);
    if (invalid || !file) return;
    await runVerify(file, documentId);
  }

  const busy = verify.isPending;
  // With exactly one document there is nothing to choose: preselect it in the "which document" prompt.
  const items = documents.data?.items ?? [];
  const pickedId = documentId || (items.length === 1 ? (items[0]?.id ?? "") : "");
  if (result) {
    return (
      <main className="mx-auto max-w-[88rem] space-y-6 px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="page-title">Verify</h1>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {user && (
              <Link to={`/verifications/${result.report.id}`} className="link">
                Open saved report
              </Link>
            )}
            <button
              type="button"
              className="btn-secondary px-4 py-2"
              onClick={() => {
                setResult(null);
                setFile(null);
                setDocumentId("");
              }}
            >
              <Icon name="refresh" className="h-4 w-4" />
              Verify another file
            </button>
          </div>
        </div>
        <Collapse open={!!user && result.report.verdict === "UNKNOWN_DOCUMENT"}>
          <div className="card mb-6 p-6 text-sm">
            <h2 className="font-display text-xl font-bold tracking-tight">
              Which document is this file a copy of?
            </h2>
            <p className="mt-1 text-gray-600 dark:text-gray-300">
              A modified file can&apos;t be matched to a document on its own. Pick the document to
              compare it against and the changes will be located.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <select
                aria-label="Document to compare against"
                value={pickedId}
                onChange={(e) => setDocumentId(e.target.value)}
                className="min-w-64 px-3 py-2"
              >
                <option value="">Select a document…</option>
                {documents.data?.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={!pickedId || busy}
                onClick={() => void runVerify(result.file, pickedId)}
                className="btn-primary"
              >
                {busy && <Spinner />}
                {busy ? "Verifying…" : "Verify against this document"}
              </button>
            </div>
            {formError && <Alert className="mt-3">{formError}</Alert>}
          </div>
        </Collapse>
        <VerificationReportView
          key={result.report.id}
          report={result.report}
          candidateFile={result.file}
          isAnonymous={!user}
        />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[88rem] px-4 py-8 sm:px-6">
      <div className="max-w-2xl">
        <p className="badge badge-accent">
          <Icon name="shield" className="h-3.5 w-3.5" />
          Public verification
        </p>
        <h1 className="page-title mt-3">Verify</h1>
        <p className="mt-2 text-base text-gray-600 dark:text-gray-300">
          Upload a PDF to check it against the approved, chain-anchored versions.
        </p>
      </div>
      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_26rem]">
        <form
          className="card space-y-6 p-6 sm:p-8"
          onSubmit={(e) => void handleSubmit(e)}
          noValidate
        >
          <div>
            <span className="eyebrow block">PDF file</span>
            <div className="mt-2">
              <FileDropzone
                accept="application/pdf,.pdf"
                selectedFileName={file?.name}
                selectedFileSize={file?.size}
                invalid={!!fileError}
                describedBy="file-error"
                onFileSelected={(f) => {
                  setFile(f);
                  // Validate on selection, so a wrong type or oversize file is flagged before submit.
                  setFileError(f ? validatePdfFile(f) : null);
                }}
              />
            </div>
            {fileError && (
              <p id="file-error" className="mt-2 text-sm text-red-600 dark:text-red-400">
                {fileError}
              </p>
            )}
          </div>

          {user && (
            <div>
              <label htmlFor="document_id" className="eyebrow block">
                Compare against a document (optional)
              </label>
              <select
                id="document_id"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                className="mt-2 w-full px-3 py-2.5"
              >
                <option value="">Detect automatically</option>
                {documents.data?.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
            </div>
          )}

          <label className="flex items-center gap-2.5 text-sm">
            <input
              type="checkbox"
              checked={includeNlp}
              onChange={(e) => setIncludeNlp(e.target.checked)}
              className="h-4 w-4"
            />
            Explain the changes (semantic analysis)
          </label>

          {formError && <Alert>{formError}</Alert>}

          <button type="submit" disabled={busy} className="btn-primary w-full py-3.5 text-base">
            {busy ? <Spinner /> : <Icon name="shield" className="h-5 w-5" />}
            {busy ? "Verifying�" : "Verify"}
          </button>
          <Collapse open={busy}>
            <UploadProgress progress={progress} />
          </Collapse>
        </form>

        <aside aria-label="How verification works" className="card space-y-5 p-6">
          <h2 className="section-title !text-base">How it works</h2>
          <ol className="space-y-5">
            {HOW_IT_WORKS.map((step, i) => (
              <li key={step.title} className="flex gap-3.5">
                <IconTile name={step.icon} className="h-10 w-10" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">
                    <span className="num text-gray-400">{i + 1}. </span>
                    {step.title}
                  </p>
                  <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="flex items-start gap-2 rounded-xl bg-blue-500/10 p-3 text-xs text-blue-900 dark:text-blue-100">
            <Icon name="lock" className="mt-0.5 h-4 w-4 shrink-0" />
            Your file is analysed and discarded; only its fingerprint is kept in the report.
          </p>
        </aside>
      </div>
    </main>
  );
}
