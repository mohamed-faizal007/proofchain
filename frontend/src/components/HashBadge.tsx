import type { ReactElement } from "react";
import { truncateHash } from "../lib/format";
import { CopyButton } from "./CopyButton";

export function HashBadge({ hash, label }: { hash: string; label?: string }): ReactElement {
  return (
    <span className="inline-flex items-center gap-1 font-mono text-xs" title={hash}>
      {label ? <span className="text-gray-500 dark:text-gray-400">{label}:</span> : null}
      <span>{truncateHash(hash)}</span>
      <CopyButton value={hash} label={label ? `Copy ${label}` : "Copy hash"} />
    </span>
  );
}
