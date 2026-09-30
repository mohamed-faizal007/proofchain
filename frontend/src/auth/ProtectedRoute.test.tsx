import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { AxiosAdapter, AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createClient } from "../api/client";
import { routerFuture } from "../routerFuture";
import { AuthProvider } from "./AuthContext";
import { ProtectedRoute } from "./ProtectedRoute";
import { setStoredToken } from "./storage";

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

function renderProtected(client: AxiosInstance, initialEntry = "/secret") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter future={routerFuture} initialEntries={[initialEntry]}>
        <AuthProvider client={client}>
          <Routes>
            <Route path="/login" element={<div>Login page</div>} />
            <Route
              path="/secret"
              element={
                <ProtectedRoute>
                  <div>Secret content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProtectedRoute", () => {
  it("redirects to /login when there is no session", async () => {
    renderProtected(createClient({ adapter: fail(401, {}) }));
    expect(await screen.findByText("Login page")).toBeInTheDocument();
  });

  it("shows a loading state while a stored token is validated, then renders children", async () => {
    setStoredToken("tok");
    const client = createClient({
      adapter: ok({
        id: "u1",
        email: "a@b.com",
        full_name: "A",
        roles: ["VERIFIER"],
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
      }),
    });
    renderProtected(client);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("Secret content")).toBeInTheDocument();
  });

  it("redirects to /login when the stored token fails validation", async () => {
    setStoredToken("bad-tok");
    const client = createClient({
      adapter: fail(401, { error: { code: "AUTH_REQUIRED", message: "Unauthorized" } }),
    });
    renderProtected(client);
    expect(await screen.findByText("Login page")).toBeInTheDocument();
  });
});
