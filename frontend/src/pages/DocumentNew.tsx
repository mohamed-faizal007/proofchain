import { zodResolver } from "@hookform/resolvers/zod";
import type { FormEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "../api/client";
import { useCreateDocument } from "../api/hooks/documents";
import type { DocType } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { FileDropzone } from "../components/FileDropzone";
import { validatePdfFile } from "../lib/pdfFile";

const DOC_TYPES: DocType[] = ["CONTRACT", "CERTIFICATE", "INVOICE", "LEGAL", "OTHER"];

const schema = z.object({
  title: z.string().min(1, "Title is required").max(200),
  doc_type: z.enum(["CONTRACT", "CERTIFICATE", "INVOICE", "LEGAL", "OTHER"]),
  change_note: z.string().max(2000).optional(),
});

type FormValues = z.infer<typeof schema>;

function mapUploadError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "This action requires the ISSUER role.";
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
        return err.message;
    }
  }
  return "Upload failed. Please try again.";
}

export function DocumentNew(): ReactElement {
  const { user } = useAuth();
  const navigate = useNavigate();
  const createDocument = useCreateDocument();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  // Guards against a double-click firing two uploads before React re-renders `isSubmitting`.
  const submittingRef = useRef(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { title: "", doc_type: "CONTRACT", change_note: "" },
  });

  if (!user?.roles.includes("ISSUER")) {
    return (
      <main className="p-6">
        <h1 className="page-title">New document</h1>
        <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
          This page requires the ISSUER role.
        </p>
      </main>
    );
  }

  const onSubmit = async (values: FormValues): Promise<void> => {
    if (submittingRef.current) return;
    if (validatePdfFile(file)) return;
    submittingRef.current = true;
    setFormError(null);
    try {
      const result = await createDocument.mutateAsync({
        file: file as File,
        title: values.title,
        doc_type: values.doc_type,
        change_note: values.change_note || undefined,
      });
      navigate(`/documents/${result.document.id}`, { replace: true });
    } catch (err) {
      setFormError(mapUploadError(err));
    } finally {
      submittingRef.current = false;
    }
  };

  const busy = isSubmitting || createDocument.isPending;

  // Runs on every submit attempt so a missing/invalid file is flagged even when RHF's own
  // field validation (title, doc_type) also fails and therefore never reaches `onSubmit`.
  function handleFormSubmit(e: FormEvent<HTMLFormElement>): void {
    setFileError(validatePdfFile(file));
    void handleSubmit(onSubmit)(e);
  }

  return (
    <main className="mx-auto mt-10 max-w-lg p-6">
      <h1 className="page-title">New document</h1>
      <form className="mt-6 space-y-4" onSubmit={handleFormSubmit} noValidate>
        <div>
          <label htmlFor="title" className="block text-sm font-medium">
            Title
          </label>
          <input
            id="title"
            type="text"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("title")}
          />
          {errors.title && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.title.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="doc_type" className="block text-sm font-medium">
            Document type
          </label>
          <select
            id="doc_type"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("doc_type")}
          >
            {DOC_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="change_note" className="block text-sm font-medium">
            Change note (optional)
          </label>
          <textarea
            id="change_note"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("change_note")}
          />
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

        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy ? "Uploading…" : "Create document"}
        </button>
      </form>
    </main>
  );
}
