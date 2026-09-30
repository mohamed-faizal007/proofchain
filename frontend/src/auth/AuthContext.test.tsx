import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createClient } from "../api/client";
import { routerFuture } from "../routerFuture";
import { AuthProvider, useAuth } from "./AuthContext";
import { getStoredToken, setStoredToken } from "./storage";

const USER = {
  id: "u1",
  email: "a@b.com",
  full_name: "A",
  roles: ["VERIFIER"] as const,
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
};

function ok(data: unknown): AxiosAdapter {
  return (config) =>
    Promise.resolve({ data, status: 200, statusText: "OK", headers: {}, config } as AxiosResponse);
}

function fail(status: number, data: unknown): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) => {
    const response = { data, status, statusText: "", headers: {}, config } as AxiosResponse;
    return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
  };
}

function Harness({ client }: { client: AxiosInstance }) {
  const { user, isLoading, login, logout, register } = useAuth();
  return (
    <div>
      <div data-testid="loading">{String(isLoading)}</div>
      <div data-testid="user">{user ? user.email : "none"}</div>
      <button
        onClick={() => void login({ email: "a@b.com", password: "secret-pass" }).catch(() => {})}
      >
        login
      </button>
      <button
        onClick={() =>
          void register({ email: "a@b.com", password: "secret-pass", full_name: "A" }).catch(
            () => {},
          )
        }
      >
        register
      </button>
      <button onClick={logout}>logout</button>
      <button onClick={() => void client.get("/documents").catch(() => {})}>make-request</button>
    </div>
  );
}

function renderHarness(client: AxiosInstance, queryClient = new QueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture}>
        <AuthProvider client={client}>
          <Harness client={client} />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuthProvider", () => {
  it("starts with no user and finishes loading when there is no stored token", async () => {
    renderHarness(createClient({ adapter: fail(401, {}) }));
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
  });

  it("validates a stored token via GET /auth/me on mount and sets the user", async () => {
    setStoredToken("tok");
    renderHarness(createClient({ adapter: ok(USER) }));
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    expect(screen.getByTestId("loading")).toHaveTextContent("false");
  });

  it("clears an invalid stored token when /auth/me rejects", async () => {
    setStoredToken("bad-tok");
    renderHarness(
      createClient({
        adapter: fail(401, { error: { code: "AUTH_REQUIRED", message: "Unauthorized" } }),
      }),
    );
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(getStoredToken()).toBeNull();
  });

  it("login stores the token and user (never the raw password)", async () => {
    const client = createClient({
      adapter: ok({ access_token: "new-tok", token_type: "bearer", user: USER }),
    });
    renderHarness(client);
    await userEvent.click(screen.getByText("login"));
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    expect(getStoredToken()).toBe("new-tok");
    expect(localStorage.getItem("secret-pass")).toBeNull();
  });

  it("logout clears the user and the stored token", async () => {
    setStoredToken("tok");
    renderHarness(createClient({ adapter: ok(USER) }));
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    await userEvent.click(screen.getByText("logout"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(getStoredToken()).toBeNull();
  });

  it("register posts to the API without changing the session", async () => {
    let posted: unknown;
    const client = createClient({
      adapter: (config) => {
        posted = config.data;
        return Promise.resolve({
          data: {},
          status: 201,
          statusText: "Created",
          headers: {},
          config,
        } as AxiosResponse);
      },
    });
    renderHarness(client);
    await userEvent.click(screen.getByText("register"));
    await waitFor(() => expect(posted).toBeDefined());
    expect(screen.getByTestId("user")).toHaveTextContent("none");
  });

  it("logs out and redirects to /login when an authenticated request returns 401", async () => {
    setStoredToken("tok");
    let meResolved = false;
    const client = createClient({
      adapter: (config) => {
        if (!meResolved && config.url?.endsWith("/auth/me")) {
          meResolved = true;
          return Promise.resolve({
            data: USER,
            status: 200,
            statusText: "OK",
            headers: {},
            config,
          } as AxiosResponse);
        }
        const response = {
          data: { error: { code: "AUTH_REQUIRED", message: "Unauthorized" } },
          status: 401,
          statusText: "",
          headers: {},
          config,
        } as AxiosResponse;
        return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
      },
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter future={routerFuture} initialEntries={["/secret"]}>
          <AuthProvider client={client}>
            <Routes>
              <Route path="/login" element={<div>Login page</div>} />
              <Route path="/secret" element={<Harness client={client} />} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    await userEvent.click(screen.getByText("make-request"));
    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
    expect(getStoredToken()).toBeNull();
  });
});

describe("AuthProvider: query cache isolation between sessions", () => {
  const KEY = ["verifications", "recent"];

  it("logout clears the query cache", async () => {
    const queryClient = new QueryClient();
    setStoredToken("tok");
    renderHarness(createClient({ adapter: ok(USER) }), queryClient);
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    queryClient.setQueryData(KEY, "user A data");
    await userEvent.click(screen.getByText("logout"));
    expect(queryClient.getQueryData(KEY)).toBeUndefined();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it("the global 401 handler clears the query cache", async () => {
    const queryClient = new QueryClient();
    setStoredToken("tok");
    const client = createClient({
      adapter: (config) =>
        config.url?.endsWith("/auth/me")
          ? ok(USER)(config)
          : fail(401, { error: { code: "AUTH_REQUIRED", message: "Unauthorized" } })(config),
    });
    renderHarness(client, queryClient);
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    queryClient.setQueryData(KEY, "user A data");
    await userEvent.click(screen.getByText("make-request"));
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));
    expect(queryClient.getQueryData(KEY)).toBeUndefined();
  });

  it("login clears leftovers from a crashed or missed-logout session BEFORE the request starts", async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(KEY, "stale data from a previous session");
    let cacheWhenLoginSent: unknown = "not called";
    const client = createClient({
      adapter: (config) => {
        cacheWhenLoginSent = queryClient.getQueryData(KEY);
        return ok({ access_token: "new-tok", token_type: "bearer", user: USER })(config);
      },
    });
    renderHarness(client, queryClient);
    await userEvent.click(screen.getByText("login"));
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    expect(cacheWhenLoginSent).toBeUndefined();
  });

  it("does not clear the cache when GET /auth/me merely rejects an expired token on mount", async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(KEY, "anonymous-visible data");
    setStoredToken("expired");
    renderHarness(
      createClient({
        adapter: fail(401, { error: { code: "AUTH_REQUIRED", message: "expired" } }),
      }),
      queryClient,
    );
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(getStoredToken()).toBeNull();
    // A silent token drop is not a logout of a real session; nothing user-specific was cached.
    expect(queryClient.getQueryData(KEY)).toBe("anonymous-visible data");
  });
});
