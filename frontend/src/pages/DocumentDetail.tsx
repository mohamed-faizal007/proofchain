import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocument, useDocumentRevisions, useProvenance } from "../api/hooks/documents";
import { useAuth } from "../auth/AuthContext";
import { RoleGate } from "../auth/RoleGate";
import { HashBadge } from "../components/HashBadge";
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
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading document…</p>
        ) : documentQuery.isError ? (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {errorMessage(documentQuery.error)}
          </p>
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
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading revisions…</p>
          ) : revisionsQuery.isError ? (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {errorMessage(revisionsQuery.error)}
            </p>
          ) : (
            <VersionTimeline revisions={revisionsQuery.data ?? []} />
          )}
        </div>
      </section>

      <section className="mt-12" aria-label="Compare revisions">
        <h2 className="section-title">Compare revisions</h2>
        <div className="mt-3">
          {revisionsQuery.isLoading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading revisions…</p>
          ) : revisionsQuery.isError ? null : (
            <RevisionDiffPanel revisions={revisionsQuery.data ?? []} />
          )}
        </div>
      </section>

      <section className="mt-12">
        <h2 className="section-title">Provenance</h2>
        <div className="mt-3">
          {provenanceQuery.isLoading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading provenance…</p>
          ) : provenanceQuery.isError ? (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {errorMessage(provenanceQuery.error)}
            </p>
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
