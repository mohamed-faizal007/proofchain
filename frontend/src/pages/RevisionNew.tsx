import type { FormEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocument, useSubmitRevision } from "../api/hooks/documents";
import { useAuth } from "../auth/AuthContext";
import { Alert } from "../components/Alert";
import { FileDropzone } from "../components/FileDropzone";
import { PageHeader } from "../components/PageHeader";
import { LoadingRegion, Skeleton } from "../components/Skeleton";
import { Spinner } from "../components/Spinner";
import { useToast } from "../components/useToast";
import { validatePdfFile } from "../lib/pdfFile";

function mapSubmitError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403)
      return "Only the owner of this document (an ISSUER) can submit revisions.";
    switch (err.code) {
      case "PENDING_REVISION_EXISTS":
        return "A revision is already waiting for approval on this document.";
      case "NO_CONTENT_CHANGE":
        return "The text of this PDF is identical to the latest approved revision.";
      case "FILE_TOO_LARGE":
        return "The file is too large for the server to accept.";
      case "INVALID_PDF":
        return "That file is not a valid PDF.";
      case "ENCRYPTED_PDF":
        return "Encrypted PDFs are not supported.";
      case "NO_EXTRACTABLE_TEXT":
        return "No extractable text was found in this PDF (scanned/image-only PDFs are not supported).";
      default:
        return err.message;
    }
  }
  return "Upload failed. Please try again.";
}

function Notice({ children }: { children: string }): ReactElement {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader icon="upload" title="New revision" />
      <Alert className="mt-6">{children}</Alert>
    </main>
  );
}

export function RevisionNew(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { notify } = useToast();
  const documentQuery = useDocument(id);
  const submitRevision = useSubmitRevision();
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  // Guards against a double-click firing two uploads before React re-renders `isPending`.
  const submittingRef = useRef(false);

  if (!user?.roles.includes("ISSUER")) return <Notice>This page requires the ISSUER role.</Notice>;

  if (documentQuery.isLoading) {
    return (
      <main className="mx-auto mt-10 max-w-lg p-6">
        <h1 className="page-title">New revision</h1>
        <LoadingRegion label="Loading document…" className="mt-6 space-y-4">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-36 w-full rounded-2xl" />
          <Skeleton className="h-10 w-full rounded-lg" />
        </LoadingRegion>
      </main>
    );
  }

  const document = documentQuery.data?.document;
  if (!document) {
    return (
      <Notice>
        {documentQuery.error instanceof ApiError
          ? documentQuery.error.message
          : "Document not found."}
      </Notice>
    );
  }
  // Backend rule: ISSUER role and document owner (documents service, P5-02).
  if (document.owner_id !== user.id) {
    return <Notice>Only the owner of this document can submit revisions.</Notice>;
  }

  const documentTitle = document.title;

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    if (submittingRef.current || !id) return;
    const fileProblem = validatePdfFile(file);
    const noteProblem = note.trim() ? null : "A change note is required.";
    setFileError(fileProblem);
    setNoteError(noteProblem);
    if (fileProblem || noteProblem) return;
    submittingRef.current = true;
    setFormError(null);
    try {
      await submitRevision.mutateAsync({
        documentId: id,
        file: file as File,
        change_note: note.trim(),
      });
      notify(`Revision submitted for "${documentTitle}". It is waiting for approval.`);
      navigate(`/documents/${id}`, { replace: true });
    } catch (err) {
      setFormError(mapSubmitError(err));
    } finally {
      submittingRef.current = false;
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader icon="upload" title="New revision">
        {document.title}
      </PageHeader>
      <form
        className="card mt-6 space-y-5 p-6 sm:p-8"
        onSubmit={(e) => {
          void handleSubmit(e);
        }}
        noValidate
      >
        <div>
          <label htmlFor="change_note" className="block text-sm font-medium">
            Change note
          </label>
          <textarea
            id="change_note"
            className="mt-1.5 w-full px-3.5 py-2.5"
            maxLength={2000}
            value={note}
            onChange={(e) => {
              setNote(e.target.value);
              setNoteError(null);
            }}
          />
          {noteError && <p className="mt-1 text-sm text-red-600 dark:text-red-400">{noteError}</p>}
        </div>

        <div>
          <span className="block text-sm font-medium">PDF file</span>
          <div className="mt-1">
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
            <p id="file-error" className="mt-1 text-sm text-red-600 dark:text-red-400">
              {fileError}
            </p>
          )}
        </div>

        {formError && <Alert>{formError}</Alert>}

        <button
          type="submit"
          disabled={submitRevision.isPending}
          className="btn-primary w-full py-3"
        >
          {submitRevision.isPending && <Spinner />}
          {submitRevision.isPending ? "Uploading…" : "Submit revision"}
        </button>
      </form>
    </main>
  );
}
