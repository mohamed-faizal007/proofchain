import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { ApiError, createClient } from "./client";

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
});
