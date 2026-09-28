import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { ApiError, createClient, setUnauthorizedHandler } from "./client";

function fail(status: number, data: unknown, headers: Record<string, string> = {}): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) => {
    const response = { data, status, statusText: "", headers, config } as AxiosResponse;
    return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
  };
}

describe("api client", () => {
  it("parses the error envelope into an ApiError", async () => {
    const client = createClient({
      adapter: fail(
        409,
        { error: { code: "REVISION_NOT_PENDING", message: "Not pending", details: { id: "r1" } } },
        { "x-request-id": "req-1" },
      ),
    });
    const err = await client.get("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const apiError = err as ApiError;
    expect(apiError.code).toBe("REVISION_NOT_PENDING");
    expect(apiError.message).toBe("Not pending");
    expect(apiError.status).toBe(409);
    expect(apiError.requestId).toBe("req-1");
    expect(apiError.details).toEqual({ id: "r1" });
  });

  it("falls back to a generic ApiError when the body is not an envelope", async () => {
    const client = createClient({ adapter: fail(502, "<html>bad gateway</html>") });
    const apiError = (await client.get("/x").catch((e: unknown) => e)) as ApiError;
    expect(apiError).toBeInstanceOf(ApiError);
    expect(apiError.code).toBe("HTTP_ERROR");
    expect(apiError.status).toBe(502);
  });

  it("attaches the bearer token when one is available", async () => {
    let seen: string | undefined;
    const adapter: AxiosAdapter = (config) => {
      seen = config.headers.get("Authorization") as string | undefined;
      return Promise.resolve({ data: {}, status: 200, statusText: "OK", headers: {}, config });
    };
    await createClient({ adapter, getToken: () => "tok" }).get("/x");
    expect(seen).toBe("Bearer tok");
  });

  it("sends no Authorization header without a token", async () => {
    let seen: unknown = "unset";
    const adapter: AxiosAdapter = (config) => {
      seen = config.headers.get("Authorization");
      return Promise.resolve({ data: {}, status: 200, statusText: "OK", headers: {}, config });
    };
    await createClient({ adapter, getToken: () => null }).get("/x");
    expect(seen).toBeUndefined();
  });

  it("invokes the unauthorized handler on a 401 from a protected endpoint", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const client = createClient({
      adapter: fail(401, { error: { code: "AUTH_REQUIRED", message: "Unauthorized" } }),
    });
    await client.get("/documents").catch(() => {});
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not invoke the unauthorized handler on a 401 from /auth/login", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const client = createClient({
      adapter: fail(401, { error: { code: "INVALID_CREDENTIALS", message: "Bad credentials" } }),
    });
    await client.post("/auth/login", {}).catch(() => {});
    expect(handler).not.toHaveBeenCalled();
  });

  it("does not invoke the unauthorized handler on a 401/403 from /auth/register", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const client = createClient({
      adapter: fail(401, { error: { code: "AUTH_REQUIRED", message: "Sign in as an admin" } }),
    });
    await client.post("/auth/register", {}).catch(() => {});
    expect(handler).not.toHaveBeenCalled();
  });
});
