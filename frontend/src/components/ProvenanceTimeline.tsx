import type { ReactElement } from "react";
import type { ProvenanceEvent } from "../api/types";
import { formatDate } from "../lib/format";

export function ProvenanceTimeline({
  events,
  chainValid,
}: {
  events: ProvenanceEvent[];
  chainValid: boolean;
}): ReactElement {
  if (events.length === 0) {
    return <p className="text-sm text-gray-500">No provenance events yet.</p>;
  }

  return (
    <div>
      {!chainValid && (
        <p role="alert" className="mb-2 text-sm font-medium text-red-600">
          The provenance hash chain for this document is broken.
        </p>
      )}
      <ul className="max-h-80 space-y-2 overflow-y-auto text-sm">
        {events.map((event) => (
          <li key={event.id} className="rounded border p-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{event.type}</span>
              <span className="text-gray-500">{formatDate(event.at)}</span>
            </div>
            <p className="text-gray-500">Actor: {event.actor_id ?? "system"}</p>
            {Object.keys(event.data).length > 0 && (
              <p className="mt-1 break-words text-gray-500">{JSON.stringify(event.data)}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
