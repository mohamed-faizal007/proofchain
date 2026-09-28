import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { HashBadge } from "./HashBadge";

const HASH = "a".repeat(64);

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HashBadge", () => {
  it("truncates the hash and shows the full value in the title", () => {
    render(<HashBadge hash={HASH} label="File hash" />);
    expect(screen.getByTitle(HASH)).toBeInTheDocument();
    expect(screen.getByText("File hash:")).toBeInTheDocument();
  });

  it("copies to the clipboard and shows a confirmation when available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<HashBadge hash={HASH} />);
    await userEvent.click(screen.getByRole("button", { name: /copy hash/i }));

    expect(writeText).toHaveBeenCalledWith(HASH);
    expect(await screen.findByText("copied")).toBeInTheDocument();
  });

  it("does not crash and shows no confirmation when the Clipboard API is unavailable", async () => {
    Object.assign(navigator, { clipboard: undefined });

    render(<HashBadge hash={HASH} />);
    await userEvent.click(screen.getByRole("button", { name: /copy hash/i }));

    expect(screen.queryByText("copied")).not.toBeInTheDocument();
  });

  it("does not crash and shows no confirmation when the clipboard write is rejected", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.assign(navigator, { clipboard: { writeText } });

    render(<HashBadge hash={HASH} />);
    await userEvent.click(screen.getByRole("button", { name: /copy hash/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.queryByText("copied")).not.toBeInTheDocument();
  });
});
