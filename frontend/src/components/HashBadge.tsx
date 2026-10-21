import type { ReactElement } from "react";
import { truncateHash } from "../lib/format";
import { CopyButton } from "./CopyButton";

export function HashBadge({ hash, label }: { hash: string; label?: string }): ReactElement {
  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-gray-100 px-2 py-1 font-mono text-xs dark:bg-gray-800/80"
      title={hash}
    >
      {label ? (
        <span className="font-sans text-[11px] text-gray-500 dark:text-gray-400">{label}:</span>
      ) : null}
      <span>{truncateHash(hash)}</span>
      <CopyButton value={hash} label={label ? `Copy ${label}` : "Copy hash"} />
    </span>
  );
}
