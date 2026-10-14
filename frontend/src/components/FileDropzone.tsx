import type { DragEvent, KeyboardEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { formatBytes } from "../lib/format";
import { MAX_UPLOAD_MB } from "../lib/pdfFile";

type DragState = "idle" | "ok" | "bad";

/** What the browser exposes mid-drag is only the MIME type (names/sizes are hidden until drop). */
function dragState(e: DragEvent<HTMLDivElement>): DragState {
  const first = e.dataTransfer.items?.[0];
  if (first && first.kind === "file" && first.type && first.type !== "application/pdf")
    return "bad";
  return "ok";
}

/** Presentational drag-and-drop + click-to-browse file picker. Callers own validation and pass
 * `invalid` (red border) plus the error text, which they render and point `describedBy` at. */
export function FileDropzone({
  accept,
  onFileSelected,
  selectedFileName,
  selectedFileSize,
  invalid = false,
  describedBy,
}: {
  accept: string;
  onFileSelected: (file: File | null) => void;
  selectedFileName?: string | null;
  selectedFileSize?: number;
  invalid?: boolean;
  describedBy?: string;
}): ReactElement {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState<DragState>("idle");

  function openPicker(): void {
    inputRef.current?.click();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>): void {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openPicker();
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>): void {
    e.preventDefault();
    setDrag("idle");
    onFileSelected(e.dataTransfer.files[0] ?? null);
  }

  const tone =
    drag === "bad" || (invalid && drag === "idle")
      ? "border-red-400 bg-red-500/5 text-red-700 dark:border-red-400/70 dark:text-red-300"
      : drag === "ok"
        ? "scale-[1.01] border-blue-500 bg-blue-500/10 text-gray-900 dark:text-white"
        : "border-gray-300 text-gray-500 hover:border-blue-400 hover:bg-blue-50/60 dark:border-gray-600 dark:hover:border-blue-400 dark:hover:bg-blue-500/10";

  return (
    <div
      role="button"
      tabIndex={0}
      data-testid="file-dropzone"
      aria-describedby={describedBy}
      onClick={openPicker}
      onKeyDown={handleKeyDown}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(dragState(e));
      }}
      onDragLeave={() => setDrag("idle")}
      onDrop={handleDrop}
      className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center text-sm transition duration-150 motion-reduce:scale-100 ${tone}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        aria-label="Choose PDF file"
        onChange={(e) => onFileSelected(e.target.files?.[0] ?? null)}
      />
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className={`mx-auto mb-3 h-8 w-8 transition-transform duration-150 ${drag === "ok" ? "-translate-y-1" : ""}`}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {selectedFileName ? (
          <path d="M7 3h7l5 5v13H7z M14 3v5h5" />
        ) : (
          <path d="M12 16V5 M7.5 9.5L12 5l4.5 4.5 M5 15v4h14v-4" />
        )}
      </svg>
      {drag === "bad" ? (
        <p className="font-medium">Only PDF files can be uploaded</p>
      ) : drag === "ok" ? (
        <p className="font-medium">Drop to select this file</p>
      ) : selectedFileName ? (
        <>
          <p className="break-all text-base font-medium text-gray-900 dark:text-gray-100">
            {selectedFileName}
          </p>
          {selectedFileSize != null && (
            <p className="mt-0.5 text-xs">
              {formatBytes(selectedFileSize)} · click or drop to replace
            </p>
          )}
        </>
      ) : (
        <>
          <p>Drag and drop a PDF here, or click to browse</p>
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            PDF only, up to {MAX_UPLOAD_MB} MB
          </p>
        </>
      )}
    </div>
  );
}
