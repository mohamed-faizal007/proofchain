import type { ReactElement } from "react";
import type { AnchorStatus, DocType, RevisionStatus } from "../api/types";
import { Icon, type IconName } from "./icons";

type Tone = "green" | "amber" | "red" | "grey" | "accent";

const STATUS: Record<RevisionStatus, { tone: Tone; icon: IconName }> = {
  PENDING: { tone: "amber", icon: "clock" },
  APPROVED: { tone: "green", icon: "checkCircle" },
  REJECTED: { tone: "red", icon: "xCircle" },
  REVOKED: { tone: "grey", icon: "x" },
};

const ANCHOR: Record<AnchorStatus, { tone: Tone; icon: IconName; label: string }> = {
  NOT_REQUESTED: { tone: "grey", icon: "link", label: "Not anchored" },
  ANCHORING: { tone: "amber", icon: "refresh", label: "Anchoring" },
  ANCHORED: { tone: "green", icon: "link", label: "Anchored" },
  FAILED: { tone: "red", icon: "alert", label: "Anchor failed" },
};

export function StatusBadge({ status }: { status: RevisionStatus }): ReactElement {
  const { tone, icon } = STATUS[status];
  return (
    <span className={`badge badge-${tone}`}>
      <Icon name={icon} className="h-3.5 w-3.5" strokeWidth={2.2} />
      {status}
    </span>
  );
}

/** The label is "Anchor: <STATUS>" so the raw status stays readable for assistive tech and tests. */
export function AnchorBadge({ status }: { status: AnchorStatus }): ReactElement {
  const { tone, icon, label } = ANCHOR[status];
  return (
    <span className={`badge badge-${tone}`} title={`Anchor: ${status}`}>
      <Icon name={icon} className="h-3.5 w-3.5" strokeWidth={2.2} />
      <span className="sr-only">Anchor: {status}. </span>
      <span aria-hidden="true">{label}</span>
    </span>
  );
}

export function TypeChip({ type }: { type: DocType }): ReactElement {
  return (
    <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-gray-600 dark:bg-gray-800 dark:text-gray-300">
      {type}
    </span>
  );
}

export function VersionBadge({ children }: { children: string }): ReactElement {
  return (
    <span className="num inline-flex items-center rounded-md bg-blue-500/10 px-2 py-0.5 text-xs font-bold text-blue-700 ring-1 ring-inset ring-blue-500/25 dark:text-blue-200">
      {children}
    </span>
  );
}

/** Tinted rounded square holding an icon; the tone follows the semantic palette. */
export function IconTile({
  name,
  tone = "accent",
  className = "h-10 w-10",
}: {
  name: IconName;
  tone?: Tone;
  className?: string;
}): ReactElement {
  const tones: Record<Tone, string> = {
    accent: "bg-blue-500/10 text-blue-600 ring-blue-500/25 dark:text-blue-300",
    green: "bg-green-500/10 text-green-600 ring-green-500/25 dark:text-green-300",
    amber: "bg-amber-500/10 text-amber-600 ring-amber-500/25 dark:text-amber-300",
    red: "bg-red-500/10 text-red-600 ring-red-500/25 dark:text-red-300",
    grey: "bg-gray-500/10 text-gray-500 ring-gray-500/25 dark:text-gray-300",
  };
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-xl ring-1 ring-inset ${tones[tone]} ${className}`}
    >
      <Icon name={name} className="h-1/2 w-1/2" />
    </span>
  );
}
