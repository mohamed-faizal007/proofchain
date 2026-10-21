import type { Verdict } from "../api/types";

export type VerdictTone = "green" | "amber" | "red" | "grey";

/** Tone per verdict (07 Theme). The label always accompanies the colour. */
export const VERDICT_INFO: Record<Verdict, { label: string; tone: VerdictTone }> = {
  AUTHENTIC_LATEST: { label: "Authentic: latest approved version", tone: "green" },
  AUTHENTIC_SUPERSEDED: { label: "Authentic, but superseded by a newer version", tone: "amber" },
  CONTENT_EQUIVALENT: { label: "Content equivalent to an approved version", tone: "amber" },
  UNAUTHORIZED_VERSION: { label: "Unauthorized version", tone: "red" },
  TAMPERED: { label: "Tampered", tone: "red" },
  RECORD_MISMATCH: { label: "Record mismatch", tone: "red" },
  UNKNOWN_DOCUMENT: { label: "Unknown document", tone: "grey" },
};

export function verdictInfo(verdict: string): { label: string; tone: VerdictTone } {
  return VERDICT_INFO[verdict as Verdict] ?? { label: verdict, tone: "grey" };
}

/** Banner surface per tone: a tinted gradient with a coloured edge, readable in both themes. */
export const TONE_CLASSES: Record<VerdictTone, string> = {
  green:
    "border-green-600/40 bg-gradient-to-br from-green-50 via-white to-green-100/60 text-green-950 dark:border-green-500/40 dark:from-green-500/20 dark:via-gray-900 dark:to-gray-900 dark:text-green-50",
  amber:
    "border-amber-500/50 bg-gradient-to-br from-amber-50 via-white to-amber-100/60 text-amber-950 dark:border-amber-400/40 dark:from-amber-500/20 dark:via-gray-900 dark:to-gray-900 dark:text-amber-50",
  red: "border-red-600/40 bg-gradient-to-br from-red-50 via-white to-red-100/60 text-red-950 dark:border-red-500/40 dark:from-red-500/20 dark:via-gray-900 dark:to-gray-900 dark:text-red-50",
  grey: "border-gray-400/50 bg-gradient-to-br from-gray-100 via-white to-gray-100 text-gray-900 dark:border-gray-500/40 dark:from-gray-700/50 dark:via-gray-900 dark:to-gray-900 dark:text-gray-100",
};

export const PILL_CLASSES: Record<VerdictTone, string> = {
  green: "badge badge-green",
  amber: "badge badge-amber",
  red: "badge badge-red",
  grey: "badge badge-grey",
};
