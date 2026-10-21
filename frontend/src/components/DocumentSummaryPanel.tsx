import type { ReactElement, ReactNode } from "react";
import type { DocumentDetailResponse, Revision } from "../api/types";
import { shortAddress } from "../lib/format";
import { AnchorBadge, StatusBadge } from "./Badges";
import { CopyButton } from "./CopyButton";
import { HashBadge } from "./HashBadge";
import { TxLink } from "./TxLink";

function Field({ label, children }: { label: string; children: ReactNode }): ReactElement {
  return (
    <div className="py-3">
      <dt className="eyebrow !text-[11px]">{label}</dt>
      <dd className="mt-1.5 flex flex-wrap items-center gap-2 text-sm">{children}</dd>
    </div>
  );
}

/** Newest revision decides the headline status: a pending one wins over the approved one it follows. */
function headlineRevision(revisions: Revision[]): Revision | undefined {
  return revisions.find((r) => r.status === "PENDING") ?? revisions[revisions.length - 1];
}

/** Sticky at-a-glance panel: status, latest approved version, hashes, chain record, actions. */
export function DocumentSummaryPanel({
  detail,
  revisions,
  actions,
}: {
  detail: DocumentDetailResponse;
  revisions: Revision[];
  actions?: ReactNode;
}): ReactElement {
  const { document: doc, latest_approved_revision: approved } = detail;
  const headline = headlineRevision(revisions);
  return (
    <aside aria-label="Summary" className="card overflow-hidden">
      <div className="bg-brand h-1" />
      <div className="p-5">
        <h2 className="section-title !text-base">Summary</h2>
        <dl className="mt-1 divide-y divide-gray-100 dark:divide-gray-800">
          <Field label="Status">
            {headline ? (
              <>
                <StatusBadge status={headline.status} />
                {headline.status === "PENDING" && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    revision {headline.revision_no}
                  </span>
                )}
              </>
            ) : (
              <span className="text-gray-500 dark:text-gray-400">No revisions</span>
            )}
          </Field>
          <Field label="Latest approved version">
            {doc.latest_approved_version_no != null ? (
              <span className="num text-base font-semibold">
                Version {doc.latest_approved_version_no}
              </span>
            ) : (
              <span className="text-gray-500 dark:text-gray-400">none yet</span>
            )}
          </Field>
          <Field label="Text root">
            {approved ? (
              <HashBadge hash={approved.text_root} label="Text root" />
            ) : (
              <span className="text-gray-400">—</span>
            )}
          </Field>
          <Field label="File hash">
            {approved ? (
              <HashBadge hash={approved.file_hash} label="File hash" />
            ) : (
              <span className="text-gray-400">—</span>
            )}
          </Field>
          <Field label="Chain record">
            {approved ? (
              <div className="w-full space-y-2">
                <AnchorBadge status={approved.anchor.status} />
                {approved.anchor.tx_hash && <TxLink txHash={approved.anchor.tx_hash} />}
                {approved.anchor.contract && (
                  <p className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Contract
                    <span className="font-mono" title={approved.anchor.contract}>
                      {shortAddress(approved.anchor.contract)}
                    </span>
                    <CopyButton value={approved.anchor.contract} label="Copy contract address" />
                  </p>
                )}
                {approved.anchor.block_number != null && (
                  <p className="num text-xs text-gray-500 dark:text-gray-400">
                    Block #{approved.anchor.block_number}
                  </p>
                )}
              </div>
            ) : (
              <span className="text-gray-500 dark:text-gray-400">
                Nothing anchored until a version is approved.
              </span>
            )}
          </Field>
        </dl>
        {actions && (
          <div className="mt-2 border-t border-gray-100 pt-4 dark:border-gray-800">{actions}</div>
        )}
      </div>
    </aside>
  );
}
