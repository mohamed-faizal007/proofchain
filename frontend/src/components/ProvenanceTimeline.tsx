import type { ReactElement } from "react";
import type { ProvenanceEvent } from "../api/types";
import { formatDate } from "../lib/format";
import { Alert } from "./Alert";
import { EmptyState } from "./EmptyState";

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
      <ul className="stagger max-h-80 space-y-2 overflow-y-auto text-sm">
        {events.map((event) => (
          <li key={event.id} className="card p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{event.type}</span>
              <span className="text-gray-500 dark:text-gray-400">{formatDate(event.at)}</span>
            </div>
            <p className="text-gray-500 dark:text-gray-400">Actor: {event.actor_id ?? "system"}</p>
            {Object.keys(event.data).length > 0 && (
              <p className="mt-1 break-words text-gray-500 dark:text-gray-400">
                {JSON.stringify(event.data)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
