import type { ReactElement, ReactNode } from "react";
import { TONE_CLASSES, verdictInfo, type VerdictTone } from "../lib/verdict";
import { Icon, type IconName } from "./icons";

const ICON_CLASSES: Record<VerdictTone, string> = {
  green: "bg-green-600 text-white shadow-[0_0_44px_rgb(34_197_94/0.5)]",
  amber: "bg-amber-500 text-white shadow-[0_0_44px_rgb(245_158_11/0.5)]",
  red: "bg-red-600 text-white shadow-[0_0_44px_rgb(239_68_68/0.55)]",
  grey: "bg-gray-500 text-white",
};

const RING_CLASSES: Record<VerdictTone, string> = {
  green: "ring-green-500/25",
  amber: "ring-amber-500/25",
  red: "ring-red-500/25",
  grey: "ring-gray-500/25",
};

const ICON_NAME: Record<VerdictTone, IconName> = {
  green: "check",
  amber: "alert",
  red: "x",
  grey: "help",
};

export interface VerdictFact {
  label: string;
  value: ReactNode;
}

/** The hero of the verify and report pages: icon, verdict, one-line explanation, key facts. */
export function VerdictBanner({
  verdict,
  summary,
  facts = [],
}: {
  verdict: string;
  summary: string;
  facts?: VerdictFact[];
}): ReactElement {
  const { label, tone } = verdictInfo(verdict);
  return (
    <section
      aria-label="Verdict"
      data-verdict={verdict}
      data-tone={tone}
      className={`animate-banner-in relative overflow-hidden rounded-3xl border p-6 shadow-lifted sm:p-9 ${TONE_CLASSES[tone]}`}
    >
      <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
        <span
          aria-hidden="true"
          className={`animate-pop-in flex h-20 w-20 shrink-0 items-center justify-center rounded-full ring-8 sm:h-24 sm:w-24 ${ICON_CLASSES[tone]} ${RING_CLASSES[tone]}`}
        >
          <Icon name={ICON_NAME[tone]} className="h-10 w-10 sm:h-12 sm:w-12" strokeWidth={2.6} />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-[0.22em] opacity-75">
            {verdict.replace(/_/g, " ")}
          </p>
          <h2 className="mt-1 font-display text-3xl font-bold leading-tight tracking-tight sm:text-5xl">
            {label}
          </h2>
          <p className="mt-3 max-w-3xl text-base opacity-90 sm:text-lg">{summary}</p>
        </div>
      </div>
      {facts.length > 0 && (
        <dl className="relative mt-7 grid gap-3 border-t border-current/10 pt-5 sm:grid-cols-2 lg:grid-cols-4">
          {facts.map((f) => (
            <div key={f.label} className="min-w-0">
              <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] opacity-65">
                {f.label}
              </dt>
              <dd className="mt-0.5 truncate text-sm font-semibold">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
