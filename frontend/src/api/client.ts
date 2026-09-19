import axios, { AxiosError, type AxiosAdapter, type AxiosInstance } from "axios";
import type { ErrorEnvelope } from "./types";

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number | null,
    readonly requestId: string | null,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isEnvelope(data: unknown): data is ErrorEnvelope {
  if (typeof data !== "object" || data === null || !("error" in data)) return false;
  const error = (data as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

export function toApiError(err: AxiosError): ApiError {
  const status = err.response?.status ?? null;
  const requestId = (err.response?.headers?.["x-request-id"] as string | undefined) ?? null;
  const data: unknown = err.response?.data;
  if (isEnvelope(data)) {
    const { code, message, details } = data.error;
    return new ApiError(code, message, status, requestId, details);
  }
  return new ApiError("HTTP_ERROR", err.message, status, requestId);
}

export interface ClientOptions {
  baseURL?: string;
  /** Returns the JWT to send, or null when signed out. Wired to auth in a later task. */
  getToken?: () => string | null;
  adapter?: AxiosAdapter;
}

export function createClient({
  baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1",
  getToken = () => null,
  adapter,
}: ClientOptions = {}): AxiosInstance {
  const client = axios.create({ baseURL, adapter });
  client.interceptors.request.use((config) => {
    const token = getToken();
    if (token) config.headers.set("Authorization", `Bearer ${token}`);
    return config;
  });
  client.interceptors.response.use(
    (response) => response,
    (err: unknown) => Promise.reject(err instanceof AxiosError ? toApiError(err) : err),
  );
  return client;
}

export const api = createClient();
