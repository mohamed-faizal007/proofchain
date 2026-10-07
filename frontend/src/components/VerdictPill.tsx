import type { ReactElement } from "react";
import { PILL_CLASSES, verdictInfo } from "../lib/verdict";

/** Compact verdict label for lists. Unknown verdict strings render as-is in grey. */
export function VerdictPill({ verdict }: { verdict: string }): ReactElement {
  const { label, tone } = verdictInfo(verdict);
  return (
    <span
      data-tone={tone}
      className={`inline-block rounded-full px-3 py-1 text-xs font-semibold ${PILL_CLASSES[tone]}`}
    >
      {label}
    </span>
  );
}
