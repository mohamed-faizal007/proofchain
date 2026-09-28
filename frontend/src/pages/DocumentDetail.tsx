import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDocument, useDocumentRevisions, useProvenance } from "../api/hooks/documents";
import { RoleGate } from "../auth/RoleGate";
import { HashBadge } from "../components/HashBadge";
import { ProvenanceTimeline } from "../components/ProvenanceTimeline";
import { VersionTimeline } from "../components/VersionTimeline";
import { formatDate } from "../lib/format";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

export function DocumentDetail(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const documentQuery = useDocument(id);
  const revisionsQuery = useDocumentRevisions(id);
  const provenanceQuery = useProvenance(id);

  return (
    <main className="mx-auto max-w-3xl p-6">
      <section>
        {documentQuery.isLoading ? (
          <p className="text-sm text-gray-500">Loading document…</p>
        ) : documentQuery.isError ? (
          <p role="alert" className="text-sm text-red-600">
            {errorMessage(documentQuery.error)}
          </p>
        ) : documentQuery.data ? (
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">{documentQuery.data.document.title}</h1>
              <p className="mt-1 text-sm text-gray-500">
                {documentQuery.data.document.doc_type} · updated{" "}
                {formatDate(documentQuery.data.document.updated_at)}
              </p>
              <p className="mt-1 text-sm text-gray-500">
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
            <RoleGate roles={["ISSUER"]}>
              <Link
                to={`/documents/${id}/revisions/new`}
                className="rounded bg-gray-900 px-4 py-2 text-sm text-white"
              >
                Submit new revision
              </Link>
            </RoleGate>
          </div>
        ) : (
          <p className="text-sm text-gray-500">Document not found.</p>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Revisions</h2>
        <div className="mt-3">
          {revisionsQuery.isLoading ? (
            <p className="text-sm text-gray-500">Loading revisions…</p>
          ) : revisionsQuery.isError ? (
            <p role="alert" className="text-sm text-red-600">
              {errorMessage(revisionsQuery.error)}
            </p>
          ) : (
            <VersionTimeline revisions={revisionsQuery.data ?? []} />
          )}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Provenance</h2>
        <div className="mt-3">
          {provenanceQuery.isLoading ? (
            <p className="text-sm text-gray-500">Loading provenance…</p>
          ) : provenanceQuery.isError ? (
            <p role="alert" className="text-sm text-red-600">
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
