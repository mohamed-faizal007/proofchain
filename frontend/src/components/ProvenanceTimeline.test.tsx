import { render, screen } from "@testing-library/react";
import type { ProvenanceEvent } from "../api/types";
import { ProvenanceTimeline } from "./ProvenanceTimeline";

function event(overrides: Partial<ProvenanceEvent> = {}): ProvenanceEvent {
  return {
    id: "e1",
    document_id: "d1",
    revision_id: "r1",
    type: "DOCUMENT_CREATED",
    actor_id: "u1",
    at: "2026-01-01T00:00:00Z",
    data: {},
    prev_event_hash: null,
    event_hash: "a".repeat(64),
    ...overrides,
  };
}

describe("ProvenanceTimeline", () => {
  it("shows an empty state with no events", () => {
    render(<ProvenanceTimeline events={[]} chainValid={true} />);
    expect(screen.getByText(/no provenance events yet/i)).toBeInTheDocument();
  });

  it("lists events with actor id (not a guessed name) and type", () => {
    render(<ProvenanceTimeline events={[event()]} chainValid={true} />);
    expect(screen.getByText("DOCUMENT_CREATED")).toBeInTheDocument();
    expect(screen.getByText("Actor: u1")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows 'system' for a null actor", () => {
    render(<ProvenanceTimeline events={[event({ actor_id: null })]} chainValid={true} />);
    expect(screen.getByText("Actor: system")).toBeInTheDocument();
  });

  it("renders event data as escaped text, never as markup", () => {
    render(
      <ProvenanceTimeline
        events={[event({ data: { note: "<img src=x onerror=alert(1)>" } })]}
        chainValid={true}
      />,
    );
    expect(document.querySelector("img")).not.toBeInTheDocument();
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
  });

  it("shows a visible warning when the hash chain is broken", () => {
    render(<ProvenanceTimeline events={[event()]} chainValid={false} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/broken/i);
  });
});
