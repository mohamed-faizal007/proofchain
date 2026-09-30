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
      <p className="text-gray-600 dark:text-gray-300">
        Chain check not performed{check?.reason ? `: ${check.reason}` : "."}
      </p>
    );
  } else if (check.ok) {
    body = (
      <p className="font-medium text-green-800 dark:text-green-200">
        ✓ Matches the on-chain record.
      </p>
    );
  } else {
    body = (
      <div className="text-red-800 dark:text-red-200">
        <p className="font-medium">✗ Does not match the on-chain record.</p>
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
    <section aria-label="Chain proof" className="rounded border p-4 text-sm">
      <h3 className="mb-2 font-semibold">Chain proof</h3>
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
