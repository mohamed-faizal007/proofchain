import type { ReactElement } from "react";
import { useChainStatus } from "../../api/hooks/chain";
import { networkName, shortAddress } from "../../lib/format";
import { Alert } from "../Alert";
import { CopyButton } from "../CopyButton";
import { Icon } from "../icons";
import { LoadingRegion, Skeleton } from "../Skeleton";

type Health = "healthy" | "down" | "off";

const HEALTH: Record<Health, { label: string; badge: string; dot: string }> = {
  healthy: { label: "Healthy", badge: "badge-green", dot: "bg-green-500" },
  down: { label: "Unreachable", badge: "badge-red", dot: "bg-red-500" },
  off: { label: "Not configured", badge: "badge-grey", dot: "bg-gray-400" },
};

function Row({
  label,
  children,
}: {
  label: string;
  children: ReactElement | string;
}): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-sm text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="flex min-w-0 items-center gap-1.5 text-sm font-medium">{children}</dd>
    </div>
  );
}

/** Where proofs are anchored: network, registry contract and the node's latest block.
 * Informational only; verification verdicts never depend on it. */
export function ChainStatusCard(): ReactElement {
  const query = useChainStatus();
  const status = query.data;
  const health: Health = !status?.configured ? "off" : status.healthy ? "healthy" : "down";
  const h = HEALTH[health];

  return (
    <section aria-label="Chain status" className="card flex flex-col p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="section-title !text-base">Chain status</h2>
        {status && (
          <span className={`badge ${h.badge}`}>
            <span className="relative flex h-2 w-2">
              {health === "healthy" && (
                <span
                  className={`absolute inline-flex h-full w-full rounded-full opacity-60 motion-safe:animate-ping ${h.dot}`}
                />
              )}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${h.dot}`} />
            </span>
            {h.label}
          </span>
        )}
      </div>

      {query.isLoading ? (
        <LoadingRegion label="Loading chain status…" className="mt-4 space-y-3">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </LoadingRegion>
      ) : query.isError || !status ? (
        <Alert className="mt-4">Chain status is unavailable right now.</Alert>
      ) : (
        <>
          <div className="mt-4 flex items-center gap-3">
            <span
              aria-hidden="true"
              className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 ring-1 ring-inset ring-blue-500/25 dark:text-blue-300"
            >
              <Icon name="cube" className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="eyebrow">Network</p>
              <p className="truncate font-display text-lg font-bold leading-tight">
                {networkName(status.chain_id)}
              </p>
            </div>
          </div>
          <dl className="mt-3 divide-y divide-gray-100 dark:divide-gray-800">
            <Row label="Contract">
              {status.contract ? (
                <>
                  <span className="font-mono text-xs" title={status.contract}>
                    {shortAddress(status.contract)}
                  </span>
                  <CopyButton value={status.contract} label="Copy contract address" />
                </>
              ) : (
                "—"
              )}
            </Row>
            <Row label="Latest block">
              <span className="num">
                {status.latest_block != null ? `#${status.latest_block}` : "—"}
              </span>
            </Row>
            {status.chain_id != null && (
              <Row label="Chain ID">
                <span className="num">{String(status.chain_id)}</span>
              </Row>
            )}
          </dl>
          <p className="mt-auto pt-4 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
            Only approved revisions are anchored. Documents never go on-chain, just their
            fingerprints.
          </p>
          {health === "down" && (
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Anchoring pauses while the node is unreachable; existing verdicts are unaffected.
            </p>
          )}
        </>
      )}
    </section>
  );
}
