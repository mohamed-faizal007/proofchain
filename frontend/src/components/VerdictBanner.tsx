import type { ReactElement } from "react";
import { TONE_CLASSES, verdictInfo, type VerdictTone } from "../lib/verdict";

const ICON_CLASSES: Record<VerdictTone, string> = {
  green: "bg-green-600 text-white",
  amber: "bg-amber-500 text-white",
  red: "bg-red-600 text-white",
  grey: "bg-gray-500 text-white",
};

const ICON_SYMBOL: Record<VerdictTone, string> = { green: "✓", amber: "!", red: "✕", grey: "?" };

export function VerdictBanner({
  verdict,
  summary,
}: {
  verdict: string;
  summary: string;
}): ReactElement {
  const { label, tone } = verdictInfo(verdict);
  return (
    <section
      aria-label="Verdict"
      data-verdict={verdict}
      data-tone={tone}
      className={`flex items-center gap-5 rounded-xl border-l-8 p-6 shadow-sm ${TONE_CLASSES[tone]}`}
    >
      <span
        aria-hidden="true"
        className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-full text-4xl font-bold ${ICON_CLASSES[tone]}`}
      >
        {ICON_SYMBOL[tone]}
      </span>
      <div className="min-w-0">
        <p className="text-xs font-bold uppercase tracking-widest opacity-80">
          {verdict.replace(/_/g, " ")}
        </p>
        <h2 className="text-3xl font-bold leading-tight">{label}</h2>
        <p className="mt-1 text-base">{summary}</p>
      </div>
    </section>
  );
}
