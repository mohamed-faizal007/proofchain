import type { ReactElement } from "react";
import type { ChainCheck, RevisionSnapshot } from "../api/types";
import { truncateHash } from "../lib/format";
import { TxLink } from "./TxLink";

const HTTP_URL_RE = /^https?:\/\//;

function TxReference({ check }: { check: ChainCheck }): ReactElement | null {
  if (!check.tx_hash) return null;
  const url = check.explorer_url;
  return (
    <p className="mt-2">
      Anchoring transaction:{" "}
      {url && HTTP_URL_RE.test(url) ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
        >
          {truncateHash(check.tx_hash)}
        </a>
      ) : (
        <TxLink txHash={check.tx_hash} />
      )}
    </p>
  );
}

/** Chain proof (07 `/verifications/:id`). Informational: the verdict is already decided. */
export function ChainProofPanel({
  check,
  revision,
}: {
  check: ChainCheck | null;
  revision: RevisionSnapshot | null;
}): ReactElement {
  let body: ReactElement;
  if (!check || !check.performed) {
    body = (
      <p className="rounded-lg bg-gray-100 px-4 py-3 text-gray-700 dark:bg-gray-800 dark:text-gray-300">
        Chain check not performed{check?.reason ? `: ${check.reason}` : "."}
      </p>
    );
  } else if (check.ok) {
    body = (
      <p className="rounded-lg bg-green-100 px-4 py-3 text-base font-semibold text-green-900 dark:bg-green-500/10 dark:text-green-300 dark:ring-1 dark:ring-inset dark:ring-green-500/30">
        ✓ Matches the on-chain record.
      </p>
    );
  } else {
    body = (
      <div className="rounded-lg bg-red-100 px-4 py-3 text-red-900 dark:bg-red-500/10 dark:text-red-300 dark:ring-1 dark:ring-inset dark:ring-red-500/30">
        <p className="text-base font-semibold">✗ Does not match the on-chain record.</p>
        {check.reason && <p>{check.reason}</p>}
        {check.mismatches.length > 0 && (
          <ul className="list-disc pl-5">
            {check.mismatches.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }
  return (
    <section aria-label="Chain proof" className="card p-6 text-sm">
      <h3 className="eyebrow mb-3">Chain proof</h3>
      {body}
      {check && <TxReference check={check} />}
      {revision && (
        <p className="mt-2 text-gray-600 dark:text-gray-300">
          Checked against revision {revision.revision_no}
          {revision.version_no != null ? ` (v${revision.version_no})` : ""}.
        </p>
      )}
    </section>
  );
}
