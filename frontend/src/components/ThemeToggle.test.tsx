import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { THEME_KEY } from "../lib/theme";
import { ThemeToggle } from "./ThemeToggle";

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.classList.remove("dark");
});

describe("ThemeToggle", () => {
  it("toggles the dark class and persists the choice", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /dark mode/i });
    expect(button).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(button);
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(button).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(button);
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
  });

  it("starts in the state already applied to <html> (set before React mounts)", () => {
    document.documentElement.classList.add("dark");
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /dark mode/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
