import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocument, useDocumentRevisions, useProvenance } from "../api/hooks/documents";
import { useAuth } from "../auth/AuthContext";
import { RoleGate } from "../auth/RoleGate";
import { Alert } from "../components/Alert";
import { HashBadge } from "../components/HashBadge";
import { CardsSkeleton, LoadingRegion, Skeleton } from "../components/Skeleton";
import { RevisionDiffPanel } from "../components/RevisionDiffPanel";
import { ProvenanceTimeline } from "../components/ProvenanceTimeline";
import { VersionTimeline } from "../components/VersionTimeline";
import { formatDate } from "../lib/format";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

export function DocumentDetail(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const documentQuery = useDocument(id);
  const revisionsQuery = useDocumentRevisions(id);
  const provenanceQuery = useProvenance(id);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <section>
        {documentQuery.isLoading ? (
          <LoadingRegion label="Loading document…" className="space-y-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-1/2" />
          </LoadingRegion>
        ) : documentQuery.isError ? (
          <Alert>{errorMessage(documentQuery.error)}</Alert>
        ) : documentQuery.data ? (
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="page-title">{documentQuery.data.document.title}</h1>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                {documentQuery.data.document.doc_type} · updated{" "}
                {formatDate(documentQuery.data.document.updated_at)}
              </p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Latest approved version:{" "}
                {documentQuery.data.document.latest_approved_version_no ?? "none yet"}
              </p>
              {documentQuery.data.latest_approved_revision && (
                <div className="mt-1">
                  <HashBadge
                    hash={documentQuery.data.latest_approved_revision.text_root}
                    label="Text root"
                  />
                </div>
              )}
            </div>
            {/* Backend rule: ISSUER role and document owner (documents service, P5-02). */}
            {user?.id === documentQuery.data.document.owner_id && (
              <RoleGate roles={["ISSUER"]}>
                <Link to={`/documents/${id}/revisions/new`} className="btn-primary">
                  Submit new revision
                </Link>
              </RoleGate>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">Document not found.</p>
        )}
      </section>

      <section className="mt-12">
        <h2 className="section-title">Revisions</h2>
        <div className="mt-3">
          {revisionsQuery.isLoading ? (
            <CardsSkeleton label="Loading revisions…" count={2} />
          ) : revisionsQuery.isError ? (
            <Alert>{errorMessage(revisionsQuery.error)}</Alert>
          ) : (
            <VersionTimeline revisions={revisionsQuery.data ?? []} />
          )}
        </div>
      </section>

      <section className="mt-12" aria-label="Compare revisions">
        <h2 className="section-title">Compare revisions</h2>
        <div className="mt-3">
          {revisionsQuery.isLoading ? (
            <LoadingRegion label="Loading revisions…">
              <Skeleton className="h-10 w-full rounded-lg" />
            </LoadingRegion>
          ) : revisionsQuery.isError ? null : (
            <RevisionDiffPanel revisions={revisionsQuery.data ?? []} />
          )}
        </div>
      </section>

      <section className="mt-12">
        <h2 className="section-title">Provenance</h2>
        <div className="mt-3">
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
    </main>
  );
}
