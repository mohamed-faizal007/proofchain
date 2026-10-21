import { formatDate, networkName, relativeTime, shortAddress, truncateHash } from "./format";

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

describe("relativeTime", () => {
  const now = Date.parse("2026-10-21T12:00:00Z");
  it("reads naturally at each scale", () => {
    expect(relativeTime("2026-10-21T11:59:50Z", now)).toBe("just now");
    expect(relativeTime("2026-10-21T11:55:00Z", now)).toBe("5 minutes ago");
    expect(relativeTime("2026-10-21T09:00:00Z", now)).toBe("3 hours ago");
    expect(relativeTime("2026-10-20T12:00:00Z", now)).toBe("yesterday");
    expect(relativeTime("2026-08-21T12:00:00Z", now)).toBe("2 months ago");
  });
  it("returns an unparsable date unchanged", () => {
    expect(relativeTime("not a date", now)).toBe("not a date");
  });
});

describe("shortAddress and networkName", () => {
  it("shortens long addresses only", () => {
    expect(shortAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")).toBe("0x5FbD…0aa3");
    expect(shortAddress("0x1234")).toBe("0x1234");
  });
  it("names known chains and falls back to the id", () => {
    expect(networkName(31337)).toBe("Hardhat local");
    expect(networkName(11155111)).toBe("Sepolia testnet");
    expect(networkName(null)).toBe("Not configured");
    expect(networkName(137)).toBe("Chain 137");
  });
});
