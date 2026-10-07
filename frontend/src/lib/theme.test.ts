import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyTheme, initTheme, resolveTheme, saveTheme, THEME_KEY } from "./theme";

function stubSystem(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: dark, addEventListener: vi.fn() }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.documentElement.classList.remove("dark");
  document.documentElement.style.colorScheme = "";
});

describe("theme", () => {
  it("defaults to dark when nothing is stored, whatever the system preference", () => {
    stubSystem(true);
    expect(resolveTheme()).toBe("dark");
    stubSystem(false);
    expect(resolveTheme()).toBe("dark");
  });

  it("a stored choice wins over the system preference", () => {
    stubSystem(true);
    localStorage.setItem(THEME_KEY, "light");
    expect(resolveTheme()).toBe("light");
  });

  it("ignores a garbage stored value", () => {
    stubSystem(false);
    localStorage.setItem(THEME_KEY, "purple");
    expect(resolveTheme()).toBe("dark");
  });

  it("applyTheme toggles the dark class and colour-scheme", () => {
    applyTheme("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    applyTheme("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("survives storage throwing on read and write", () => {
    stubSystem(true);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(resolveTheme()).toBe("dark");
    expect(() => saveTheme("light")).not.toThrow();
    expect(() => initTheme()).not.toThrow();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("works when matchMedia is missing", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(resolveTheme()).toBe("dark");
  });
});

// The React entry only runs after the bundle loads, so a stored dark choice would flash light.
// index.html therefore carries a tiny blocking script; it must agree with lib/theme.ts.
describe("index.html no-flash script", () => {
  const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8");
  const match = /<script>([\s\S]*?)<\/script>/.exec(html);

  function runInline(): void {
    if (!match) throw new Error("inline theme script missing from index.html");
    new Function(match[1])();
  }

  it("is a blocking inline script placed before the module entry", () => {
    expect(match).not.toBeNull();
    expect(html.indexOf(match?.[0] ?? "")).toBeLessThan(html.indexOf('type="module"'));
  });

  it("applies the stored dark theme before React mounts", () => {
    stubSystem(false);
    localStorage.setItem(THEME_KEY, "dark");
    runInline();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("defaults to dark even when the system prefers light, and agrees with resolveTheme", () => {
    stubSystem(false);
    runInline();
    expect(document.documentElement).toHaveClass("dark");
    expect(resolveTheme()).toBe("dark");
  });

  it("a stored light choice still wins", () => {
    stubSystem(true);
    localStorage.setItem(THEME_KEY, "light");
    runInline();
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("does not throw when storage is blocked", () => {
    stubSystem(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(runInline).not.toThrow();
    expect(document.documentElement).toHaveClass("dark");
  });
});
