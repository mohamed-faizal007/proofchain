import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router-dom";
import { api } from "../api/client";
import { useRecentVerifications } from "../api/hooks/verifications";
import { routerFuture } from "../routerFuture";
import { AuthProvider, useAuth } from "./AuthContext";

const userFor = (name: string) => ({
  id: `id-${name}`,
  email: `${name}@example.com`,
  full_name: name,
  roles: ["VERIFIER"],
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
});

const reply = (config: InternalAxiosRequestConfig, data: unknown): AxiosResponse => ({
  data,
  status: 200,
  statusText: "OK",
  headers: {},
  config,
});

const page = (filename: string) => ({
  items: [
    {
      id: `ver-${filename}`,
      at: "2026-09-30T10:00:00Z",
      verdict: "TAMPERED",
      summary: "s",
      document: null,
      filename,
      file_hash: "a".repeat(64),
    },
  ],
  page: 1,
  page_size: 5,
  total: 1,
});

/** Reads the signed-in user's history through the real query hook. */
function History() {
  const query = useRecentVerifications(5);
  if (query.isLoading) return <p>history loading</p>;
  return (
    <ul>
      {query.data?.items.map((v) => (
        <li key={v.id}>{v.filename}</li>
      ))}
    </ul>
  );
}

function Harness() {
  const { user, login, logout } = useAuth();
  return (
    <div>
      <p data-testid="who">{user ? user.full_name : "nobody"}</p>
      <button onClick={() => void login({ email: "A@example.com", password: "password-a" })}>
        login A
      </button>
      <button onClick={() => void login({ email: "B@example.com", password: "password-b" })}>
        login B
      </button>
      <button onClick={logout}>logout</button>
      {user && <History />}
    </div>
  );
}

describe("two users, one browser", () => {
  it("never shows user A's cached data to user B, even before B's own fetch resolves", async () => {
    let releaseB: () => void = () => {};
    const bGate = new Promise<void>((resolve) => {
      releaseB = resolve;
    });
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      const url = String(config.url);
      if (url === "/auth/login") {
        const email = (JSON.parse(String(config.data)) as { email: string }).email;
        const name = email.startsWith("A") ? "A" : "B";
        return Promise.resolve(
          reply(config, { access_token: `tok-${name}`, token_type: "bearer", user: userFor(name) }),
        );
      }
      if (url === "/verifications") {
        const auth = String(config.headers.get("Authorization"));
        if (auth === "Bearer tok-A") return Promise.resolve(reply(config, page("A-secret.pdf")));
        if (auth === "Bearer tok-B") return bGate.then(() => reply(config, page("B-own.pdf")));
      }
      return Promise.reject(new Error(`unexpected ${url}`));
    }) as AxiosAdapter;

    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter future={routerFuture}>
          <AuthProvider>
            <Harness />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // User A signs in and their history is fetched and cached.
    await userEvent.click(screen.getByText("login A"));
    expect(await screen.findByText("A-secret.pdf")).toBeInTheDocument();

    // A signs out; nothing of A's is left on screen.
    await userEvent.click(screen.getByText("logout"));
    expect(screen.getByTestId("who")).toHaveTextContent("nobody");
    expect(screen.queryByText("A-secret.pdf")).not.toBeInTheDocument();

    // B signs in. B's fetch is held open: A's cached list must NOT appear in the meantime.
    await userEvent.click(screen.getByText("login B"));
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("B"));
    expect(screen.getByText("history loading")).toBeInTheDocument();
    expect(screen.queryByText("A-secret.pdf")).not.toBeInTheDocument();

    // Only B's own data shows once it arrives.
    releaseB();
    expect(await screen.findByText("B-own.pdf")).toBeInTheDocument();
    expect(screen.queryByText("A-secret.pdf")).not.toBeInTheDocument();
  });
});
