import type { ReactElement } from "react";
import { useState } from "react";
import { truncateHash } from "../lib/format";

const COPIED_MESSAGE_MS = 1500;

export function HashBadge({ hash, label }: { hash: string; label?: string }): ReactElement {
  const [copied, setCopied] = useState(false);

  async function handleCopy(): Promise<void> {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(hash);
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPIED_MESSAGE_MS);
    } catch {
      // Clipboard write denied/unavailable: no crash, no confirmation shown.
    }
  }

  return (
    <span className="inline-flex items-center gap-1 font-mono text-xs" title={hash}>
      {label ? <span className="text-gray-500">{label}:</span> : null}
      <span>{truncateHash(hash)}</span>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={label ? `Copy ${label}` : "Copy hash"}
        className="text-gray-400 hover:text-gray-700"
      >
        ⧉
      </button>
      {copied && (
        <span role="status" className="text-green-600">
          copied
        </span>
      )}
    </span>
  );
}
