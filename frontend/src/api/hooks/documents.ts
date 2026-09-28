import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  DocType,
  DocumentCreateResponse,
  Document,
  DocumentDetailResponse,
  Paginated,
  Provenance,
  Revision,
  RevisionStatus,
} from "../types";

export interface DocumentFilters {
  q?: string;
  doc_type?: DocType;
  status?: RevisionStatus;
  page: number;
  page_size: number;
}

/** GET /documents (04_API_SPEC): paginated, filtered by literal `q`, `doc_type`, `status`. */
export function useDocuments(filters: DocumentFilters) {
  return useQuery({
    queryKey: ["documents", filters],
    queryFn: async () => {
      const { data } = await api.get<Paginated<Document>>("/documents", { params: filters });
      return data;
    },
  });
}

/** GET /documents/{id} (04_API_SPEC): the document plus its newest APPROVED revision (or null). */
export function useDocument(documentId: string | undefined) {
  return useQuery({
    queryKey: ["documents", documentId],
    queryFn: async () => {
      const { data } = await api.get<DocumentDetailResponse>(`/documents/${documentId}`);
      return data;
    },
    enabled: documentId != null,
  });
}

/** GET /documents/{id}/revisions (04_API_SPEC): all revisions, ascending revision_no. */
export function useDocumentRevisions(documentId: string | undefined) {
  return useQuery({
    queryKey: ["documents", documentId, "revisions"],
    queryFn: async () => {
      const { data } = await api.get<Revision[]>(`/documents/${documentId}/revisions`);
      return data;
    },
    enabled: documentId != null,
  });
}

/** GET /documents/{id}/provenance (04_API_SPEC): ordered events + chain-hash-chain validity. */
export function useProvenance(documentId: string | undefined) {
  return useQuery({
    queryKey: ["documents", documentId, "provenance"],
    queryFn: async () => {
      const { data } = await api.get<Provenance>(`/documents/${documentId}/provenance`);
      return data;
    },
    enabled: documentId != null,
  });
}

export interface CreateDocumentInput {
  file: File;
  title: string;
  doc_type: DocType;
  change_note?: string;
}

/** POST /documents (multipart): creates the document + its first PENDING revision. */
export function useCreateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateDocumentInput) => {
      const form = new FormData();
      form.append("file", input.file);
      form.append("title", input.title);
      form.append("doc_type", input.doc_type);
      if (input.change_note) form.append("change_note", input.change_note);
      const { data } = await api.post<DocumentCreateResponse>("/documents", form);
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
