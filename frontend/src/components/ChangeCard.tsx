import type { ReactElement } from "react";
import type { AnalysisItem, ChangeRegion, DiffOp, EntityChange } from "../api/types";

const SEVERITY_CLASSES: Record<string, string> = {
  LOW: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-100",
  MEDIUM: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-200",
  HIGH: "bg-orange-200 text-orange-950 dark:bg-orange-900 dark:text-orange-100",
  CRITICAL: "bg-red-200 text-red-950 dark:bg-red-900 dark:text-red-100",
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
      className={`rounded-lg border bg-gray-50 p-4 text-sm dark:bg-gray-800 ${selected ? "border-blue-500 ring-2 ring-blue-300" : ""}`}
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
            <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-900">
              {pretty(analysis.primary_category)}
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[analysis.severity] ?? ""}`}
            >
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
