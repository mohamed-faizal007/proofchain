import { formatDate, truncateHash } from "./format";

describe("formatDate", () => {
  it("formats a valid ISO datetime as a non-empty locale string", () => {
    const formatted = formatDate("2026-01-15T10:30:00Z");
    expect(formatted.length).toBeGreaterThan(0);
    expect(formatted).not.toBe("2026-01-15T10:30:00Z");
  });

  it("returns the original string unchanged for an invalid date", () => {
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });
});

describe("truncateHash", () => {
  it("shortens a 64-char hex hash to a head…tail form", () => {
    const hash = "a".repeat(60) + "f9e8";
    expect(truncateHash(hash)).toBe("aaaaaa…f9e8");
  });

  it("returns short strings unchanged", () => {
    expect(truncateHash("short")).toBe("short");
  });
});
