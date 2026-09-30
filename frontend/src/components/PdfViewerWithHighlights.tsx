import { useEffect, useRef, useState } from "react";
import { useRevisionPdf } from "../api/hooks/useRevisionPdf";
import { useFileBytes } from "../lib/useFileBytes";
import { highlightsForPage, type PageHighlight } from "../lib/bbox";
import { openPdf, type PdfPageLike } from "../lib/pdfjs";
import { HighlightLegend } from "./HighlightOverlay";
import { PdfPage } from "./PdfPage";

export interface PdfViewerProps {
  /** A stored revision, downloaded through the authenticated client. */
  revisionId?: string;
  /** Alternatively an in-memory file (e.g. a verification upload that is never stored). */
  file?: File;
  highlights: PageHighlight[];
  /** Id of the highlight to emphasise and scroll to. */
  focusedId?: string;
}

interface LoadedPage {
  page: PdfPageLike;
  widthPts: number;
  heightPts: number;
}

const FALLBACK_WIDTH = 800;
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.25;

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(w);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Views one revision's PDF with bbox highlight overlays (07 "Highlight overlay").
 * The bytes come through the authenticated API client; pdf.js gets an ArrayBuffer, so no
 * object URL is ever created. Import via LazyPdfViewer to keep pdf.js out of the main bundle. */
export default function PdfViewerWithHighlights({
  revisionId,
  file,
  highlights,
  focusedId,
}: PdfViewerProps) {
  const remote = useRevisionPdf(file ? undefined : revisionId);
  const local = useFileBytes(file);
  const pdf = file ? local : remote;
  const [pages, setPages] = useState<LoadedPage[] | null>(null);
  const [parseError, setParseError] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [containerRef, containerWidth] = useElementWidth<HTMLDivElement>();

  useEffect(() => {
    if (!pdf.data) return;
    let cancelled = false;
    let doc: Awaited<ReturnType<typeof openPdf>> | null = null;
    setPages(null);
    setParseError(false);
    openPdf(pdf.data)
      .then(async (opened) => {
        doc = opened;
        const loaded = await Promise.all(
          Array.from({ length: opened.numPages }, async (_, i) => {
            const page = await opened.getPage(i + 1);
            const { width, height } = page.getViewport({ scale: 1 });
            return { page, widthPts: width, heightPts: height };
          }),
        );
        if (!cancelled) setPages(loaded);
      })
      .catch(() => {
        if (!cancelled) setParseError(true);
      });
    return () => {
      cancelled = true;
      void doc?.destroy();
    };
  }, [pdf.data]);

  const fitWidth = containerWidth > 0 ? containerWidth : FALLBACK_WIDTH;
  const renderedWidth = fitWidth * zoom;

  let body;
  if (pdf.isError) {
    body = (
      <div
        role="alert"
        className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
      >
        Could not load the PDF: {pdf.error?.message ?? "unknown error"}{" "}
        <button type="button" className="underline" onClick={() => void pdf.refetch()}>
          Retry
        </button>
      </div>
    );
  } else if (parseError) {
    body = (
      <div
        role="alert"
        className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
      >
        This file is not a readable PDF.
      </div>
    );
  } else if (!pages) {
    body = (
      <p role="status" className="p-6 text-center text-sm text-gray-500">
        Loading PDF…
      </p>
    );
  } else if (pages.length === 0) {
    body = <p className="p-6 text-center text-sm text-gray-500">This PDF has no pages.</p>;
  } else {
    body = (
      <div className="space-y-6 py-4">
        {pages.map((p, i) => (
          <PdfPage
            key={i}
            page={p.page}
            index={i}
            widthPts={p.widthPts}
            heightPts={p.heightPts}
            renderedWidth={renderedWidth}
            highlights={highlightsForPage(highlights, i)}
            showEmptyHint={highlights.length > 0}
            focusedId={focusedId}
          />
        ))}
      </div>
    );
  }

  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button
          type="button"
          aria-label="Zoom out"
          disabled={zoom <= ZOOM_MIN}
          className="rounded border px-2 disabled:opacity-40"
          onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z - ZOOM_STEP))}
        >
          −
        </button>
        <span aria-live="polite" className="w-12 text-center">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          aria-label="Zoom in"
          disabled={zoom >= ZOOM_MAX}
          className="rounded border px-2 disabled:opacity-40"
          onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z + ZOOM_STEP))}
        >
          +
        </button>
        <button type="button" className="rounded border px-2" onClick={() => setZoom(1)}>
          Fit width
        </button>
        {highlights.length > 0 && <HighlightLegend />}
      </div>
      <div ref={containerRef} className="overflow-x-auto bg-gray-100">
        {body}
      </div>
    </section>
  );
}
