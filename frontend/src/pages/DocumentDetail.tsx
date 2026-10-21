import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocument, useDocumentRevisions, useProvenance } from "../api/hooks/documents";
import { useAuth } from "../auth/AuthContext";
import { RoleGate } from "../auth/RoleGate";
import { Alert } from "../components/Alert";
import { TypeChip } from "../components/Badges";
import { DocumentSummaryPanel } from "../components/DocumentSummaryPanel";
import { Icon } from "../components/icons";
import { CardsSkeleton, LoadingRegion, Skeleton } from "../components/Skeleton";
import { RevisionDiffPanel } from "../components/RevisionDiffPanel";
import { ProvenanceTimeline } from "../components/ProvenanceTimeline";
import { VersionTimeline } from "../components/VersionTimeline";
import { formatDate, relativeTime } from "../lib/format";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

export function DocumentDetail(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const documentQuery = useDocument(id);
  const revisionsQuery = useDocumentRevisions(id);
  const provenanceQuery = useProvenance(id);

  const detail = documentQuery.data;
  // Backend rule: ISSUER role and document owner (documents service, P5-02).
  const canSubmit = !!detail && user?.id === detail.document.owner_id;

  return (
    <main className="mx-auto max-w-[88rem] space-y-8 px-4 py-8 sm:px-6">
      <header>
        {documentQuery.isLoading ? (
          <LoadingRegion label="Loading document…" className="space-y-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
          </LoadingRegion>
        ) : documentQuery.isError ? (
          <Alert>{errorMessage(documentQuery.error)}</Alert>
        ) : detail ? (
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-4">
              <span
                aria-hidden="true"
                className="bg-brand hidden h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-white shadow-glow sm:flex"
              >
                <Icon name="document" className="h-7 w-7" />
              </span>
              <div className="min-w-0">
                <h1 className="page-title">{detail.document.title}</h1>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <TypeChip type={detail.document.doc_type} />
                  <span>
                    <time
                      dateTime={detail.document.updated_at}
                      title={formatDate(detail.document.updated_at)}
                    >
                      updated {relativeTime(detail.document.updated_at)}
                    </time>
                  </span>
                  <span className="num">· {detail.document.revision_count} revisions</span>
                </p>
              </div>
            </div>
            {canSubmit && (
              <RoleGate roles={["ISSUER"]}>
                <Link to={`/documents/${id}/revisions/new`} className="btn-primary px-5 py-2.5">
                  <Icon name="plus" className="h-4 w-4" strokeWidth={2.4} />
                  Submit new revision
                </Link>
              </RoleGate>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">Document not found.</p>
        )}
      </header>

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_24rem]">
        {/* Summary first in the DOM so it leads on narrow screens; it moves to the right from lg. */}
        <div className="space-y-4 lg:sticky lg:top-24 lg:order-2">
          {documentQuery.isLoading ? (
            <LoadingRegion label="Loading summary…" className="card space-y-3 p-5">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-6 w-1/2" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
            </LoadingRegion>
          ) : detail ? (
            <DocumentSummaryPanel
              detail={detail}
              revisions={revisionsQuery.data ?? []}
              actions={
                canSubmit ? (
                  <RoleGate roles={["ISSUER"]}>
                    <Link to={`/documents/${id}/revisions/new`} className="btn-secondary w-full">
                      <Icon name="upload" className="h-4 w-4" />
                      Upload a new revision
                    </Link>
                  </RoleGate>
                ) : undefined
              }
            />
          ) : null}
        </div>

        <div className="min-w-0 space-y-10 lg:order-1">
          <section aria-label="Revisions">
            <h2 className="section-title">Revisions</h2>
            <div className="mt-4">
              {revisionsQuery.isLoading ? (
                <CardsSkeleton label="Loading revisions…" count={2} />
              ) : revisionsQuery.isError ? (
                <Alert>{errorMessage(revisionsQuery.error)}</Alert>
              ) : (
                <VersionTimeline revisions={revisionsQuery.data ?? []} />
              )}
            </div>
          </section>

          <section aria-label="Compare revisions">
            <h2 className="section-title">Compare revisions</h2>
            <div className="mt-4">
              {revisionsQuery.isLoading ? (
                <LoadingRegion label="Loading revisions…">
                  <Skeleton className="h-10 w-full rounded-lg" />
                </LoadingRegion>
              ) : revisionsQuery.isError ? null : (
                <RevisionDiffPanel revisions={revisionsQuery.data ?? []} />
              )}
            </div>
          </section>

          <section aria-label="Provenance">
            <h2 className="section-title">Provenance</h2>
            <div className="mt-4">
              {provenanceQuery.isLoading ? (
                <CardsSkeleton label="Loading provenance…" count={2} />
              ) : provenanceQuery.isError ? (
                <Alert>{errorMessage(provenanceQuery.error)}</Alert>
              ) : (
                <ProvenanceTimeline
                  events={provenanceQuery.data?.events ?? []}
                  chainValid={provenanceQuery.data?.chain_valid ?? true}
                />
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
