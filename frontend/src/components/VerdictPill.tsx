import type { ReactElement } from "react";
import { PILL_CLASSES, verdictInfo, type VerdictTone } from "../lib/verdict";
import { Icon, type IconName } from "./icons";

const TONE_ICON: Record<VerdictTone, IconName> = {
  green: "checkCircle",
  amber: "alert",
  red: "xCircle",
  grey: "help",
};

/** Compact verdict label for lists. Unknown verdict strings render as-is in grey. */
export function VerdictPill({ verdict }: { verdict: string }): ReactElement {
  const { label, tone } = verdictInfo(verdict);
  return (
    <span data-tone={tone} className={PILL_CLASSES[tone]}>
      <Icon name={TONE_ICON[tone]} className="h-3.5 w-3.5 shrink-0" strokeWidth={2.2} />
      {label}
    </span>
  );
}
