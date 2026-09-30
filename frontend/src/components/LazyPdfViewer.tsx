import { lazy, Suspense } from "react";
import type { PdfViewerProps } from "./PdfViewerWithHighlights";

// pdf.js is large: load the viewer (and pdf.js, dynamically imported inside it) on demand.
const PdfViewerWithHighlights = lazy(() => import("./PdfViewerWithHighlights"));

export default function LazyPdfViewer(props: PdfViewerProps) {
  return (
    <Suspense
      fallback={
        <p role="status" className="p-6 text-center text-sm text-gray-500 dark:text-gray-400">
          Loading viewer…
        </p>
      }
    >
      <PdfViewerWithHighlights {...props} />
    </Suspense>
  );
}
