import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { prefersReducedMotion } from "../lib/motion";
import { Collapse } from "./Collapse";
import { ToastProvider } from "./Toast";
import { useToast } from "./useToast";

function mockMatchMedia(reduce: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
    })),
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("prefersReducedMotion", () => {
  it("is true without matchMedia (jsdom) so nothing waits on an animation", () => {
    expect(prefersReducedMotion()).toBe(true);
  });

  it("follows the media query when it exists", () => {
    mockMatchMedia(false);
    expect(prefersReducedMotion()).toBe(false);
    mockMatchMedia(true);
    expect(prefersReducedMotion()).toBe(true);
  });
});

describe("Collapse", () => {
  beforeEach(() => vi.useFakeTimers());

  it("plays an exit animation, then unmounts, when motion is allowed", () => {
    mockMatchMedia(false);
    const { rerender } = render(
      <Collapse open>
        <button type="button">inside</button>
      </Collapse>,
    );
    expect(screen.getByRole("button", { name: "inside" })).toBeInTheDocument();

    rerender(
      <Collapse open={false}>
        <button type="button">inside</button>
      </Collapse>,
    );
    const button = screen.getByRole("button", { name: "inside" });
    expect(button.closest(".animate-collapse-close")).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(screen.queryByRole("button", { name: "inside" })).not.toBeInTheDocument();
  });

  it("opens with the open animation class", () => {
    mockMatchMedia(false);
    render(
      <Collapse open>
        <p>hello</p>
      </Collapse>,
    );
    expect(screen.getByText("hello").closest(".animate-collapse-open")).not.toBeNull();
  });

  it("unmounts immediately under reduced motion", () => {
    mockMatchMedia(true);
    const { rerender } = render(
      <Collapse open>
        <p>hello</p>
      </Collapse>,
    );
    rerender(
      <Collapse open={false}>
        <p>hello</p>
      </Collapse>,
    );
    expect(screen.queryByText("hello")).not.toBeInTheDocument();
  });
});

function Trigger({ message }: { message: string }) {
  const { notify } = useToast();
  return (
    <button type="button" onClick={() => notify(message)}>
      go
    </button>
  );
}

describe("Toast", () => {
  it("shows a toast, lets the user dismiss it, and auto-dismisses otherwise", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger message="Saved it" />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "go" }));
    expect(screen.getByText("Saved it")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /dismiss notification/i }));
    expect(screen.queryByText("Saved it")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "go" }));
    expect(screen.getByText("Saved it")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Saved it")).not.toBeInTheDocument();
  });

  it("is a harmless no-op outside a provider", () => {
    render(<Trigger message="Nobody listens" />);
    fireEvent.click(screen.getByRole("button", { name: "go" }));
    expect(screen.queryByText("Nobody listens")).not.toBeInTheDocument();
  });
});
