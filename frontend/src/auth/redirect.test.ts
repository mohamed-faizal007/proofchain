import { safeRedirectPath } from "./redirect";

describe("safeRedirectPath", () => {
  it("returns an internal path unchanged", () => {
    expect(safeRedirectPath("/documents/123")).toBe("/documents/123");
  });

  const unsafe: (string | null | undefined)[] = [
    undefined,
    null,
    "",
    "//evil.com",
    "https://evil.com",
    "http://evil.com/x",
    "/\\evil.com",
    "evil.com",
  ];

  it.each(unsafe)("falls back to / for %j", (input) => {
    expect(safeRedirectPath(input)).toBe("/");
  });
});
