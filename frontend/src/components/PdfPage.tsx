import { useEffect, useRef, useState } from "react";
import { fitScale, type PageHighlight } from "../lib/bbox";
import type { PdfPageLike } from "../lib/pdfjs";
import { HighlightOverlay } from "./HighlightOverlay";

interface Props {
  page: PdfPageLike;
  /** 0-based page index. */
  index: number;
  widthPts: number;
  heightPts: number;
  renderedWidth: number;
  highlights: PageHighlight[];
  /** True when the document has highlights somewhere, so an empty page deserves a hint. */
  showEmptyHint: boolean;
  focusedId?: string;
}

/** Renders the canvas only while the page is (nearly) on screen; otherwise a same-sized
 * placeholder keeps the scroll height stable. */
export function PdfPage({
  page,
  index,
  widthPts,
  heightPts,
  renderedWidth,
  highlights,
  showEmptyHint,
  focusedId,
}: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");
  const [renderError, setRenderError] = useState(false);

  const scale = fitScale(renderedWidth, widthPts);
  const rotated = page.rotate % 360 !== 0;

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const last = entries[entries.length - 1];
        if (last) setVisible(last.isIntersecting);
      },
      { rootMargin: "400px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!visible || !canvas || scale <= 0) return;
    setRenderError(false);
    const viewport = page.getViewport({ scale: scale * (window.devicePixelRatio || 1) });
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    const task = page.render({ canvas, viewport });
    let cancelled = false;
    task.promise.catch(() => {
      if (!cancelled) setRenderError(true); // a cancelled render rejects; that is expected
    });
    return () => {
      cancelled = true;
      task.cancel();
    };
  }, [page, visible, scale]);

  return (
    <div
      ref={wrapperRef}
      data-testid={`pdf-page-${index + 1}`}
      className="relative mx-auto bg-white shadow"
      style={{ width: renderedWidth, height: heightPts * scale }}
    >
      {visible && <canvas ref={canvasRef} className="h-full w-full" />}
      {renderError && (
        <p role="alert" className="absolute inset-x-0 top-2 text-center text-xs text-red-700">
          Could not render page {index + 1}.
        </p>
      )}
      {rotated ? (
        <p className="absolute inset-x-0 bottom-2 mx-2 rounded bg-yellow-100 p-1 text-center text-xs text-yellow-900">
          This page is rotated ({page.rotate}°); change highlights are not shown for rotated pages.
        </p>
      ) : (
        <>
          <HighlightOverlay highlights={highlights} scale={scale} focusedId={focusedId} />
          {showEmptyHint && highlights.length === 0 && (
            <p className="absolute inset-x-0 bottom-2 text-center text-xs text-gray-500">
              No highlighted changes on this page.
            </p>
          )}
        </>
      )}
    </div>
  );
}
