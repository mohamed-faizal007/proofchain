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

/** Mutable module state backing the shared `api` client's token and session-expiry handling. */
let currentToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

/** Sets the bearer token clients created here attach by default (AuthContext calls this). */
export function setAuthToken(token: string | null): void {
  currentToken = token;
}

/** Registers the callback fired when an authenticated request comes back 401 (session expiry). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

/** Endpoints where a 401 must not trigger the global sign-out + redirect: it has a domain meaning
 * (bad credentials, restricted registration) or the caller handles it itself. `/auth/me` runs on
 * every page load with whatever token is stored, so an expired token there is dropped silently
 * (AuthProvider) and must not bounce a visitor off the public /verify and /register pages;
 * `/verify` is public, so its 401 (PUBLIC_VERIFY=false) is shown by the page. ProtectedRoute
 * still redirects anonymous visitors on protected routes. */
const AUTH_EXEMPT_SUFFIXES = ["/auth/login", "/auth/register", "/auth/me", "/verify"];

function isAuthExempt(url: string | undefined): boolean {
  return url != null && AUTH_EXEMPT_SUFFIXES.some((suffix) => url.endsWith(suffix));
}

export interface ClientOptions {
  baseURL?: string;
  /** Returns the JWT to send, or null when signed out. Defaults to the shared module token. */
  getToken?: () => string | null;
  adapter?: AxiosAdapter;
}

export function createClient({
  baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1",
  getToken = () => currentToken,
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
    (err: unknown) => {
      const apiError = err instanceof AxiosError ? toApiError(err) : err;
      const url = err instanceof AxiosError ? err.config?.url : undefined;
      if (apiError instanceof ApiError && apiError.status === 401 && !isAuthExempt(url)) {
        unauthorizedHandler?.();
      }
      return Promise.reject(apiError);
    },
  );
  return client;
}

export const api = createClient();
