import type { ReactElement } from "react";
import type { AnalysisItem, ChangeRegion, DiffOp, EntityChange } from "../api/types";

const SEVERITY_CLASSES: Record<string, string> = {
  LOW: "badge-grey",
  MEDIUM: "badge-amber",
  HIGH: "bg-orange-50 text-orange-800 ring-orange-600/25 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/30",
  CRITICAL: "badge-red",
};

const pretty = (s: string): string => s.replace(/_/g, " ").toLowerCase();

function TokenDiff({ ops }: { ops: DiffOp[] }): ReactElement {
  return (
    <p
      aria-label="Token diff"
      className="rounded bg-gray-50 p-2 font-mono text-xs dark:bg-gray-800"
    >
      {ops.map((op, i) => (
        <span key={i}>
          {op.op === "equal" && `${op.after.join(" ")} `}
          {(op.op === "delete" || op.op === "replace") && (
            <del className="bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-200">
              {op.before.join(" ")}{" "}
            </del>
          )}
          {(op.op === "insert" || op.op === "replace") && (
            <ins className="bg-green-100 text-green-900 no-underline dark:bg-green-900 dark:text-green-200">
              {op.after.join(" ")}{" "}
            </ins>
          )}
        </span>
      ))}
    </p>
  );
}

function Entity({ change }: { change: EntityChange }): ReactElement {
  return (
    <li>
      <span className="text-gray-500 dark:text-gray-400">{pretty(change.type)}:</span>{" "}
      {change.before === null ? (
        <span>added {change.after}</span>
      ) : change.after === null ? (
        <span>removed {change.before}</span>
      ) : (
        <span>
          <del>{change.before}</del> → <ins className="no-underline">{change.after}</ins>
        </span>
      )}
    </li>
  );
}

/** One change. `analysis` is absent when NLP was skipped; its sections are then simply omitted. */
export function ChangeCard({
  region,
  analysis,
  selected,
  onSelect,
}: {
  region: ChangeRegion;
  analysis?: AnalysisItem;
  selected: boolean;
  onSelect: (id: string) => void;
}): ReactElement {
  const page = region.cand_page ?? region.ref_page;
  return (
    <li
      data-testid={`change-${region.id}`}
      className={`rounded-xl border bg-gray-50/80 p-4 text-sm transition-all dark:bg-gray-800/50 ${selected ? "border-blue-500 shadow-glow ring-2 ring-blue-400/50" : "hover:border-gray-300 dark:hover:border-gray-600"}`}
    >
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(region.id)}
        className="flex w-full flex-wrap items-center gap-2 text-left"
      >
        <span className="font-semibold">{region.type[0] + region.type.slice(1).toLowerCase()}</span>
        {page != null && <span className="text-gray-600 dark:text-gray-300">page {page + 1}</span>}
        {analysis && (
          <>
            <span className="badge badge-accent">{pretty(analysis.primary_category)}</span>
            <span className={`badge ${SEVERITY_CLASSES[analysis.severity] ?? "badge-grey"}`}>
              {analysis.severity.toLowerCase()} severity
            </span>
          </>
        )}
      </button>
      {analysis && (
        <div className="mt-2 space-y-2">
          {analysis.explanation && <p>{analysis.explanation}</p>}
          {analysis.entity_changes.length > 0 && (
            <ul className="list-disc pl-5">
              {analysis.entity_changes.map((c, i) => (
                <Entity key={i} change={c} />
              ))}
            </ul>
          )}
          {analysis.token_diff && analysis.token_diff.length > 0 && (
            <TokenDiff ops={analysis.token_diff} />
          )}
        </div>
      )}
    </li>
  );
}
