import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type {
  DocType,
  DocumentCreateResponse,
  Document,
  Paginated,
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
