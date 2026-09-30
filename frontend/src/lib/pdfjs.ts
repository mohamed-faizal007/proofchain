/** Thin, mockable wrapper around pdf.js. Imported dynamically (see LazyPdfViewer) so the
 * ~1MB library and its worker stay out of the main bundle. */

export interface PdfViewport {
  width: number;
  height: number;
}
export interface PdfRenderTask {
  promise: Promise<unknown>;
  cancel(): void;
}
export interface PdfPageLike {
  /** Page rotation in degrees as reported by pdf.js itself (`/Rotate`). */
  rotate: number;
  getViewport(params: { scale: number }): PdfViewport;
  render(params: { canvas: HTMLCanvasElement; viewport: PdfViewport }): PdfRenderTask;
}
export interface PdfDocLike {
  numPages: number;
  getPage(pageNumber: number): Promise<PdfPageLike>;
  destroy(): Promise<void>;
}

/** Hardening for untrusted PDFs. pdf.js has no `enableScripting` getDocument option: scripting
 * only runs via its viewer/scripting manager, which we never use (canvas only, no annotation
 * or text layer, so no links or form widgets exist to click). */
export const PDF_LOAD_OPTIONS = {
  isEvalSupported: false,
  enableXfa: false,
  disableAutoFetch: true,
  disableStream: true,
} as const;

export async function openPdf(data: ArrayBuffer): Promise<PdfDocLike> {
  const pdfjs = await import("pdfjs-dist");
  const { default: workerSrc } = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
  pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
  // pdf.js transfers (detaches) the buffer to its worker: hand it a copy so the cached one survives.
  const task = pdfjs.getDocument({ data: new Uint8Array(data.slice(0)), ...PDF_LOAD_OPTIONS });
  return (await task.promise) as unknown as PdfDocLike;
}
