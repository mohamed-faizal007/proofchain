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
  green: "border-green-600 bg-green-50 text-green-900",
  amber: "border-amber-500 bg-amber-50 text-amber-900",
  red: "border-red-600 bg-red-50 text-red-900",
  grey: "border-gray-400 bg-gray-50 text-gray-800",
};
