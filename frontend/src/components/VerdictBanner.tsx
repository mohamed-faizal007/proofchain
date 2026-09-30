import type { ReactElement } from "react";
import { TONE_CLASSES, verdictInfo } from "../lib/verdict";

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
      className={`rounded border-l-4 p-4 ${TONE_CLASSES[tone]}`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide">{verdict.replace(/_/g, " ")}</p>
      <h2 className="text-xl font-semibold">{label}</h2>
      <p className="mt-1 text-sm">{summary}</p>
    </section>
  );
}
