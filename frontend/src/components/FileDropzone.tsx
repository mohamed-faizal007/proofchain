import type { DragEvent, KeyboardEvent, ReactElement } from "react";
import { useRef, useState } from "react";

/** Presentational drag-and-drop + click-to-browse file picker. Callers own validation. */
export function FileDropzone({
  accept,
  onFileSelected,
  selectedFileName,
}: {
  accept: string;
  onFileSelected: (file: File | null) => void;
  selectedFileName?: string | null;
}): ReactElement {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

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
    setDragOver(false);
    onFileSelected(e.dataTransfer.files[0] ?? null);
  }

  return (
    <div
      role="button"
      tabIndex={0}
      data-testid="file-dropzone"
      onClick={openPicker}
      onKeyDown={handleKeyDown}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center text-sm transition-colors ${
        dragOver
          ? "border-blue-500 bg-blue-500/10 text-gray-900 dark:text-white"
          : "border-gray-300 text-gray-500 hover:border-blue-400 hover:bg-blue-50/60 dark:border-gray-600 dark:hover:border-blue-400 dark:hover:bg-blue-500/10"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        aria-label="Choose PDF file"
        onChange={(e) => onFileSelected(e.target.files?.[0] ?? null)}
      />
      {selectedFileName ? (
        <p className="text-base font-medium text-gray-900 dark:text-gray-100">{selectedFileName}</p>
      ) : (
        <p>Drag and drop a PDF here, or click to browse</p>
      )}
    </div>
  );
}
