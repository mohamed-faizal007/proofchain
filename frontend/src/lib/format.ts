export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

export function truncateHash(hash: string): string {
  if (hash.length <= 12) return hash;
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "3 hours ago", "yesterday"; falls back to the raw string for an unparsable date. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((then - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "just now";
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of RELATIVE_UNITS) {
    if (abs >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(Math.round(seconds / 60), "minute");
}

/** `0x5FbD…0aa3`: first 6 and last 4 characters of an address. */
export function shortAddress(address: string): string {
  if (address.length <= 12) return address;
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

/** Human name of a well-known EVM chain id; the number itself otherwise. */
export function networkName(chainId: number | null): string {
  switch (chainId) {
    case 31337:
      return "Hardhat local";
    case 11155111:
      return "Sepolia testnet";
    case 1:
      return "Ethereum mainnet";
    case null:
      return "Not configured";
    default:
      return `Chain ${chainId}`;
  }
}
