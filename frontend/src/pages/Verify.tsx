import type { FormEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocuments } from "../api/hooks/documents";
import { useVerify } from "../api/hooks/verifications";
import type { VerificationReport } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { FileDropzone } from "../components/FileDropzone";
import { VerificationReportView } from "../components/VerificationReportView";
import { validatePdfFile } from "../lib/pdfFile";

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

  async function runVerify(upload: File, againstDocumentId: string): Promise<void> {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setFormError(null);
    try {
      const report = await verify.mutateAsync({
        file: upload,
        documentId: againstDocumentId || undefined,
        includeNlp,
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
      <main className="mx-auto max-w-6xl p-6">
        <h1 className="text-3xl font-bold tracking-tight">Verify</h1>
        <div className="my-4 flex items-center gap-4 text-sm">
          <button
            type="button"
            className="rounded-lg border bg-white px-4 py-2 font-medium shadow-sm hover:bg-gray-50 dark:bg-gray-900 dark:hover:bg-gray-800"
            onClick={() => {
              setResult(null);
              setFile(null);
            }}
          >
            Verify another file
          </button>
          {user && (
            <Link
              to={`/verifications/${result.report.id}`}
              className="text-blue-600 underline dark:text-blue-400"
            >
              Open saved report
            </Link>
          )}
        </div>
        {user && result.report.verdict === "UNKNOWN_DOCUMENT" && (
          <div className="mb-5 rounded-xl border bg-white p-5 text-sm shadow-sm dark:bg-gray-900">
            <h2 className="text-base font-semibold">Which document is this file a copy of?</h2>
            <p className="mt-1 text-gray-600 dark:text-gray-300">
              A modified file can&apos;t be matched to a document on its own. Pick the document to
              compare it against and the changes will be located.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <select
                aria-label="Document to compare against"
                value={pickedId}
                onChange={(e) => setDocumentId(e.target.value)}
                className="min-w-64 rounded-lg border px-3 py-2 dark:bg-gray-800"
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
                className="rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
              >
                {busy ? "Verifying…" : "Verify against this document"}
              </button>
            </div>
            {formError && (
              <p role="alert" className="mt-2 text-red-600 dark:text-red-400">
                {formError}
              </p>
            )}
          </div>
        )}
        <VerificationReportView
          report={result.report}
          candidateFile={result.file}
          isAnonymous={!user}
        />
      </main>
    );
  }

  return (
    <main className="mx-auto mt-10 max-w-xl p-6">
      <h1 className="text-3xl font-bold tracking-tight">Verify</h1>
      <p className="mt-2 text-gray-600 dark:text-gray-300">
        Upload a PDF to check it against the approved, chain-anchored versions.
      </p>
      <form
        className="mt-6 space-y-5 rounded-xl border bg-white p-6 shadow-sm dark:bg-gray-900"
        onSubmit={(e) => void handleSubmit(e)}
        noValidate
      >
        <div>
          <span className="block text-sm font-medium">PDF file</span>
          <div className="mt-1">
            <FileDropzone
              accept="application/pdf,.pdf"
              selectedFileName={file?.name}
              onFileSelected={(f) => {
                setFile(f);
                setFileError(null);
              }}
            />
          </div>
          {fileError && <p className="mt-1 text-sm text-red-600 dark:text-red-400">{fileError}</p>}
        </div>

        {user && (
          <div>
            <label htmlFor="document_id" className="block text-sm font-medium">
              Compare against a document (optional)
            </label>
            <select
              id="document_id"
              value={documentId}
              onChange={(e) => setDocumentId(e.target.value)}
              className="mt-1 w-full rounded-lg border px-3 py-2 dark:bg-gray-800"
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

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeNlp}
            onChange={(e) => setIncludeNlp(e.target.checked)}
          />
          Explain the changes (semantic analysis)
        </label>

        {formError && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {formError}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-blue-600 px-4 py-3 text-base font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "Verifying…" : "Verify"}
        </button>
      </form>
    </main>
  );
}
