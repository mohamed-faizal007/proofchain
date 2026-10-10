import type { FormEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocument, useSubmitRevision } from "../api/hooks/documents";
import { useAuth } from "../auth/AuthContext";
import { FileDropzone } from "../components/FileDropzone";
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
    <main className="p-6">
      <h1 className="page-title">New revision</h1>
      <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
        {children}
      </p>
    </main>
  );
}

export function RevisionNew(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
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
      <main className="p-6">
        <h1 className="page-title">New revision</h1>
        <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">Loading document…</p>
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
      navigate(`/documents/${id}`, { replace: true });
    } catch (err) {
      setFormError(mapSubmitError(err));
    } finally {
      submittingRef.current = false;
    }
  }

  return (
    <main className="mx-auto mt-10 max-w-lg p-6">
      <h1 className="page-title">New revision</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{document.title}</p>
      <form
        className="mt-6 space-y-4"
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
            className="mt-1 w-full rounded border px-3 py-2"
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
              onFileSelected={(f) => {
                setFile(f);
                setFileError(null);
              }}
            />
          </div>
          {fileError && <p className="mt-1 text-sm text-red-600 dark:text-red-400">{fileError}</p>}
        </div>

        {formError && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {formError}
          </p>
        )}

        <button type="submit" disabled={submitRevision.isPending} className="btn-primary w-full">
          {submitRevision.isPending ? "Uploading…" : "Submit revision"}
        </button>
      </form>
    </main>
  );
}
