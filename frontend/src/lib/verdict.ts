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

export const TONE_CLASSES: Record<VerdictTone, string> = {
  green:
    "border-green-600 bg-green-100 text-green-950 dark:border-green-500 dark:bg-gray-900 dark:bg-gradient-to-r dark:from-green-500/20 dark:to-green-950/60 dark:text-green-50",
  amber:
    "border-amber-500 bg-amber-100 text-amber-950 dark:border-amber-400 dark:bg-gray-900 dark:bg-gradient-to-r dark:from-amber-500/20 dark:to-amber-950/60 dark:text-amber-50",
  red: "border-red-600 bg-red-100 text-red-950 dark:border-red-500 dark:bg-gray-900 dark:bg-gradient-to-r dark:from-red-500/20 dark:to-red-950/60 dark:text-red-50",
  grey: "border-gray-400 bg-gray-100 text-gray-900 dark:border-gray-500 dark:bg-gray-900 dark:bg-gradient-to-r dark:from-gray-700/60 dark:to-gray-900 dark:text-gray-100",
};

export const PILL_CLASSES: Record<VerdictTone, string> = {
  green:
    "bg-green-100 text-green-900 dark:bg-green-500/15 dark:text-green-300 dark:ring-1 dark:ring-inset dark:ring-green-500/30",
  amber:
    "bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-1 dark:ring-inset dark:ring-amber-500/30",
  red: "bg-red-100 text-red-900 dark:bg-red-500/15 dark:text-red-300 dark:ring-1 dark:ring-inset dark:ring-red-500/30",
  grey: "bg-gray-100 text-gray-800 dark:bg-gray-700/60 dark:text-gray-200 dark:ring-1 dark:ring-inset dark:ring-gray-600",
};
