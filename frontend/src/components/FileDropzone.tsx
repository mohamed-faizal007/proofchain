import type { DragEvent, KeyboardEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { formatBytes } from "../lib/format";
import { MAX_UPLOAD_MB } from "../lib/pdfFile";
import { Icon } from "./icons";

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
        ? "scale-[1.01] border-blue-500 bg-blue-500/10 text-gray-900 shadow-glow dark:text-white"
        : selectedFileName
          ? "border-green-500/50 bg-green-500/5 text-gray-600 hover:border-green-500 dark:text-gray-300"
          : "border-gray-300 bg-gray-50/60 text-gray-500 hover:border-blue-400 hover:bg-blue-50/60 dark:border-gray-600 dark:bg-gray-900/40 dark:hover:border-blue-400 dark:hover:bg-blue-500/10";

  const badTone = drag === "bad" || (invalid && drag === "idle");
  const iconTone = badTone
    ? "bg-red-500/15 text-red-500 ring-red-500/30"
    : selectedFileName && drag === "idle"
      ? "bg-green-500/15 text-green-600 ring-green-500/30 dark:text-green-300"
      : "bg-brand text-white shadow-glow ring-white/20";

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
      className={`group cursor-pointer rounded-3xl border-2 border-dashed px-6 py-12 text-center text-sm transition duration-150 motion-reduce:scale-100 sm:py-14 ${tone}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        aria-label="Choose PDF file"
        onChange={(e) => onFileSelected(e.target.files?.[0] ?? null)}
      />
      <span
        aria-hidden="true"
        className={`mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl ring-1 ring-inset transition-transform duration-150 ${iconTone} ${drag === "ok" ? "-translate-y-1.5" : "group-hover:-translate-y-0.5"}`}
      >
        <Icon
          name={badTone ? "alert" : selectedFileName && drag === "idle" ? "file" : "upload"}
          className="h-8 w-8"
          strokeWidth={1.6}
        />
      </span>
      {drag === "bad" ? (
        <p className="text-base font-semibold">Only PDF files can be uploaded</p>
      ) : drag === "ok" ? (
        <p className="text-base font-semibold">Drop to select this file</p>
      ) : selectedFileName ? (
        <>
          <p className="break-all text-lg font-semibold text-gray-900 dark:text-gray-100">
            {selectedFileName}
          </p>
          {selectedFileSize != null && (
            <p className="mt-1 text-xs">
              {formatBytes(selectedFileSize)} � click or drop to replace
            </p>
          )}
        </>
      ) : (
        <>
          <p className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Drag and drop a PDF here, or click to browse
          </p>
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            PDF only, up to {MAX_UPLOAD_MB} MB
          </p>
        </>
      )}
    </div>
  );
}
