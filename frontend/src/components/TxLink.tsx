import type { ReactElement } from "react";
import { truncateHash } from "../lib/format";

const TX_HASH_RE = /^0x[0-9a-fA-F]{64}$/;
const HTTP_URL_RE = /^https?:\/\//;

export interface TxLinkProps {
  txHash: string | null;
  /** Defaults to the build-time explorer base URL; overridable for tests. */
  explorerBaseUrl?: string;
}

/** Links to a block explorer when both the configured base URL and the tx hash look genuine
 * (P5-04: an ANCHORED revision can have `tx_hash: null` when recovered as already on-chain). */
export function TxLink({
  txHash,
  explorerBaseUrl = import.meta.env.VITE_EXPLORER_TX_URL,
}: TxLinkProps): ReactElement {
  if (!txHash) {
    return <span className="text-gray-500 dark:text-gray-400">anchored (tx not recorded)</span>;
  }
  const hasValidBase = typeof explorerBaseUrl === "string" && HTTP_URL_RE.test(explorerBaseUrl);
  const hasValidHash = TX_HASH_RE.test(txHash);
  if (!hasValidBase || !hasValidHash) {
    return <span className="font-mono text-xs">{truncateHash(txHash)}</span>;
  }
  return (
    <a
      href={`${explorerBaseUrl}${txHash}`}
      target="_blank"
      rel="noopener noreferrer"
      className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
    >
      {truncateHash(txHash)}
    </a>
  );
}
