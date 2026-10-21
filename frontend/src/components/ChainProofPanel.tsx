import type { ReactElement } from "react";
import type { ChainCheck, RevisionSnapshot } from "../api/types";
import { truncateHash } from "../lib/format";
import { Icon } from "./icons";
import { TxLink } from "./TxLink";

const HTTP_URL_RE = /^https?:\/\//;

function TxReference({ check }: { check: ChainCheck }): ReactElement | null {
  if (!check.tx_hash) return null;
  const url = check.explorer_url;
  return (
    <p className="mt-4 flex flex-wrap items-center gap-2 text-gray-600 dark:text-gray-300">
      Anchoring transaction:{" "}
      {url && HTTP_URL_RE.test(url) ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2 py-1 font-mono text-xs text-blue-600 hover:underline dark:bg-gray-800/80 dark:text-blue-300"
        >
          {truncateHash(check.tx_hash)}
          <Icon name="external" className="h-3 w-3" />
        </a>
      ) : (
        <TxLink txHash={check.tx_hash} />
      )}
    </p>
  );
}

function Result({
  tone,
  icon,
  children,
}: {
  tone: "green" | "red" | "grey";
  icon: "check" | "x" | "help";
  children: ReactElement | ReactElement[];
}): ReactElement {
  const cls = {
    green: "bg-green-500/10 text-green-900 ring-green-600/25 dark:text-green-200",
    red: "bg-red-500/10 text-red-900 ring-red-600/25 dark:text-red-200",
    grey: "bg-gray-100 text-gray-800 ring-gray-400/30 dark:bg-gray-800 dark:text-gray-200",
  }[tone];
  const dot = {
    green: "bg-green-600 text-white",
    red: "bg-red-600 text-white",
    grey: "bg-gray-400 text-white",
  }[tone];
  return (
    <div className={`flex items-start gap-3.5 rounded-xl px-4 py-3.5 ring-1 ring-inset ${cls}`}>
      <span
        aria-hidden="true"
        className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${dot}`}
      >
        <Icon name={icon} className="h-4 w-4" strokeWidth={2.6} />
      </span>
      <div className="min-w-0">{children}</div>
    </div>
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
      <Result tone="grey" icon="help">
        <p>Chain check not performed{check?.reason ? `: ${check.reason}` : "."}</p>
      </Result>
    );
  } else if (check.ok) {
    body = (
      <Result tone="green" icon="check">
        <p className="text-base font-semibold">Matches the on-chain record.</p>
      </Result>
    );
  } else {
    body = (
      <Result tone="red" icon="x">
        <p className="text-base font-semibold">Does not match the on-chain record.</p>
        {check.reason ? <p>{check.reason}</p> : <></>}
        {check.mismatches.length > 0 ? (
          <ul className="mt-1 list-disc pl-5">
            {check.mismatches.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        ) : (
          <></>
        )}
      </Result>
    );
  }
  return (
    <section aria-label="Chain proof" className="card p-6 text-sm">
      <div className="mb-4 flex items-center gap-2">
        <Icon name="link" className="h-4 w-4 text-blue-500" />
        <h3 className="eyebrow">Chain proof</h3>
      </div>
      {body}
      {check && <TxReference check={check} />}
      {revision && (
        <p className="mt-3 text-gray-600 dark:text-gray-300">
          Checked against revision {revision.revision_no}
          {revision.version_no != null ? ` (v${revision.version_no})` : ""}.
        </p>
      )}
    </section>
  );
}
