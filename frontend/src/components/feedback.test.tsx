import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, vi } from "vitest";
import { Alert } from "./Alert";
import { EmptyState } from "./EmptyState";
import { CardsSkeleton, LoadingRegion, RowsSkeleton } from "./Skeleton";
import { TxLink } from "./TxLink";

afterEach(() => vi.restoreAllMocks());

describe("Alert", () => {
  it("errors are announced as alerts, success as status", () => {
    render(
      <>
        <Alert>Bad thing</Alert>
        <Alert variant="success">Good thing</Alert>
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Bad thing");
    expect(screen.getByRole("status")).toHaveTextContent("Good thing");
  });

  it("can be silent for state that is already on the page at load", () => {
    render(<Alert live={false}>Anchoring failed</Alert>);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Anchoring failed")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("shows the explanation and the action that fills the list", () => {
    render(
      <EmptyState title="Nothing yet" action={<a href="/new">Add one</a>}>
        Add your first item.
      </EmptyState>,
    );
    expect(screen.getByText("Nothing yet")).toBeInTheDocument();
    expect(screen.getByText("Add your first item.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add one" })).toBeInTheDocument();
  });
});

describe("skeletons", () => {
  it("expose one labelled busy status each instead of a pile of blocks", () => {
    render(
      <>
        <LoadingRegion label="Loading things…">
          <div />
        </LoadingRegion>
        <RowsSkeleton label="Loading rows…" />
        <CardsSkeleton label="Loading cards…" />
      </>,
    );
    expect(screen.getByText("Loading things…")).toHaveClass("sr-only");
    expect(screen.getByText("Loading rows…")).toBeInTheDocument();
    expect(screen.getByText("Loading cards…")).toBeInTheDocument();
    expect(screen.getAllByRole("status")).toHaveLength(3);
    for (const region of screen.getAllByRole("status")) {
      expect(region).toHaveAttribute("aria-busy", "true");
    }
  });
});

describe("TxLink copy", () => {
  const TX = `0x${"b".repeat(64)}`;

  it("copies the full transaction hash and confirms it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<TxLink txHash={TX} explorerBaseUrl="https://sepolia.etherscan.io/tx/" />);
    await userEvent.click(screen.getByRole("button", { name: /copy transaction hash/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(TX));
    expect(await screen.findByText("copied")).toBeInTheDocument();
  });
});

describe("reduced motion", () => {
  const css = readFileSync(resolve(__dirname, "../index.css"), "utf-8");

  it("the stylesheet switches off animations and transitions when the user asks", () => {
    const block = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(block).toMatch(/animation-duration: 0\.01ms !important/);
    expect(block).toMatch(/transition-duration: 0\.01ms !important/);
    // The spinner is the one essential signal: it pulses instead of rotating.
    expect(block).toMatch(/\.spinner[^}]*pulse-soft/);
  });

  it("hover lift on buttons only applies where motion is safe", () => {
    expect(css).toMatch(/motion-safe:enabled:hover:-translate-y-px/);
  });
});
