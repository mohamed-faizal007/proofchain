import { useEffect, useRef } from "react";
import { bboxToRect, type HighlightType, type PageHighlight } from "../lib/bbox";

/** Colour AND text label AND border style, so meaning never depends on colour alone. */
const HIGHLIGHT_STYLES: Record<
  HighlightType,
  { label: string; box: string; chip: string; swatch: string }
> = {
  MODIFIED: {
    label: "Modified",
    box: "border-solid border-amber-500 bg-amber-300/30",
    chip: "bg-amber-500 text-black",
    swatch: "border-solid border-amber-500 bg-amber-300/40",
  },
  INSERTED: {
    label: "Inserted",
    box: "border-dashed border-green-600 bg-green-300/30",
    chip: "bg-green-700 text-white",
    swatch: "border-dashed border-green-600 bg-green-300/40",
  },
  DELETED: {
    label: "Deleted",
    box: "border-dotted border-red-600 bg-red-300/30",
    chip: "bg-red-700 text-white",
    swatch: "border-dotted border-red-600 bg-red-300/40",
  },
};

function Box({
  highlight,
  scale,
  focused,
}: {
  highlight: PageHighlight;
  scale: number;
  focused: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focused) ref.current?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }, [focused]);

  const rect = bboxToRect(highlight.bbox, scale);
  if (!rect) return null;
  const style = HIGHLIGHT_STYLES[highlight.type];
  return (
    <div
      ref={ref}
      role="img"
      aria-label={`${style.label} region`}
      data-testid={`highlight-${highlight.id}`}
      className={`pointer-events-none absolute border-2 ${style.box} ${
        focused ? "ring-2 ring-blue-500 ring-offset-1" : ""
      }`}
      style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
    >
      <span
        className={`absolute -top-4 left-0 whitespace-nowrap rounded px-1 text-[10px] font-semibold leading-4 ${style.chip}`}
      >
        {style.label}
      </span>
    </div>
  );
}

export function HighlightOverlay({
  highlights,
  scale,
  focusedId,
}: {
  highlights: PageHighlight[];
  scale: number;
  focusedId?: string;
}) {
  return (
    <div className="pointer-events-none absolute inset-0">
      {highlights.map((h) => (
        <Box key={h.id} highlight={h} scale={scale} focused={h.id === focusedId} />
      ))}
    </div>
  );
}

export function HighlightLegend() {
  return (
    <ul aria-label="Highlight legend" className="flex flex-wrap gap-3 text-xs">
      {(Object.keys(HIGHLIGHT_STYLES) as HighlightType[]).map((type) => (
        <li key={type} className="flex items-center gap-1">
          <span
            aria-hidden="true"
            className={`inline-block h-3 w-4 border-2 ${HIGHLIGHT_STYLES[type].swatch}`}
          />
          {HIGHLIGHT_STYLES[type].label}
        </li>
      ))}
    </ul>
  );
}
