import type { ReactElement, ReactNode } from "react";
import { IconTile } from "../Badges";
import type { IconName } from "../icons";

type Tone = "accent" | "green" | "amber" | "red" | "grey";

const EDGE: Record<Tone, string> = {
  accent: "from-blue-400 to-blue-600",
  green: "from-green-400 to-emerald-600",
  amber: "from-amber-300 to-orange-500",
  red: "from-red-400 to-rose-600",
  grey: "from-gray-400 to-gray-600",
};

const GLOW: Record<Tone, string> = {
  accent: "bg-blue-500/15",
  green: "bg-green-500/15",
  amber: "bg-amber-500/15",
  red: "bg-red-500/15",
  grey: "bg-gray-500/10",
};

/** One headline number with a label, an icon, a secondary line and an accent edge. The value
 * (or its loading/error state) is passed in, so each tile keeps its own query state. */
export function StatTile({
  icon,
  label,
  tone = "accent",
  hint,
  children,
}: {
  icon: IconName;
  label: string;
  tone?: Tone;
  hint?: ReactNode;
  children: ReactNode;
}): ReactElement {
  return (
    <div className="card relative overflow-hidden p-5">
      <span
        aria-hidden="true"
        className={`absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r ${EDGE[tone]}`}
      />
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full blur-2xl ${GLOW[tone]}`}
      />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">{label}</p>
          <div className="mt-2">{children}</div>
        </div>
        <IconTile name={icon} tone={tone} className="h-11 w-11" />
      </div>
      {hint && (
        <p className="relative mt-3 border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
          {hint}
        </p>
      )}
    </div>
  );
}

/** The big number inside a StatTile. */
export function StatValue({ children }: { children: ReactNode }): ReactElement {
  return (
    <p className="num text-4xl font-bold leading-none tracking-tight text-gray-900 dark:text-white">
      {children}
    </p>
  );
}
