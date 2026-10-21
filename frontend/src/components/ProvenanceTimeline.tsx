import type { ReactElement } from "react";
import type { ProvenanceEvent } from "../api/types";
import { formatDate, relativeTime } from "../lib/format";
import { Alert } from "./Alert";
import { EmptyState } from "./EmptyState";
import { Icon, type IconName } from "./icons";

const EVENT_STYLE: Record<string, { icon: IconName; label: string; cls: string }> = {
  DOCUMENT_CREATED: { icon: "document", label: "Document created", cls: "text-blue-500" },
  REVISION_SUBMITTED: { icon: "upload", label: "Revision submitted", cls: "text-blue-500" },
  REVISION_APPROVED: { icon: "checkCircle", label: "Revision approved", cls: "text-green-500" },
  REVISION_REJECTED: { icon: "xCircle", label: "Revision rejected", cls: "text-red-500" },
  VERSION_ANCHORED: { icon: "link", label: "Anchored on-chain", cls: "text-green-500" },
  ANCHOR_FAILED: { icon: "alert", label: "Anchoring failed", cls: "text-red-500" },
  VERSION_REVOKED: { icon: "x", label: "Version revoked", cls: "text-red-500" },
};

const FALLBACK = { icon: "spark" as IconName, label: "", cls: "text-gray-500" };

/** The audit trail, oldest first as the server sends it, with the raw event code kept visible. */
export function ProvenanceTimeline({
  events,
  chainValid,
}: {
  events: ProvenanceEvent[];
  chainValid: boolean;
}): ReactElement {
  if (events.length === 0) {
    return (
      <div className="card">
        <EmptyState title="No provenance events yet">
          Every upload, approval and anchoring step is recorded here as it happens.
        </EmptyState>
      </div>
    );
  }

  return (
    <div>
      {!chainValid && (
        <Alert className="mb-3">The provenance hash chain for this document is broken.</Alert>
      )}
      <div className="card p-5">
        <ol className="scroll-thin stagger max-h-[26rem] overflow-y-auto pr-2 text-sm">
          {events.map((event, i) => {
            const style = EVENT_STYLE[event.type] ?? FALLBACK;
            const last = i === events.length - 1;
            return (
              <li key={event.id} className="relative flex gap-3.5 pb-5 last:pb-0">
                {!last && (
                  <span
                    aria-hidden="true"
                    className="absolute bottom-0 left-[0.9rem] top-8 w-px bg-gray-200 dark:bg-gray-700"
                  />
                )}
                <span
                  aria-hidden="true"
                  className={`relative z-[1] flex h-[1.9rem] w-[1.9rem] shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800 ${style.cls}`}
                >
                  <Icon name={style.icon} className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {style.label && <span className="font-semibold">{style.label}</span>}
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                      {event.type}
                    </span>
                    <time
                      dateTime={event.at}
                      title={formatDate(event.at)}
                      className="ml-auto text-xs text-gray-500 dark:text-gray-400"
                    >
                      {relativeTime(event.at)}
                    </time>
                  </div>
                  <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                    Actor: {event.actor_id ?? "system"}
                  </p>
                  {Object.keys(event.data).length > 0 && (
                    <p className="mt-1.5 break-words rounded-lg bg-gray-50 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-gray-600 dark:bg-gray-800/60 dark:text-gray-300">
                      {JSON.stringify(event.data)}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
