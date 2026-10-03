import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createClient } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { routerFuture } from "../routerFuture";
import { Login } from "./Login";

const USER = {
  id: "u1",
  email: "a@b.com",
  full_name: "A",
  roles: ["VERIFIER"],
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

function renderLogin(
  client: AxiosInstance,
  initialEntries: (string | { pathname: string; state?: unknown })[] = ["/login"],
) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter future={routerFuture} initialEntries={initialEntries}>
        <AuthProvider client={client}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<div>Dashboard page</div>} />
            <Route path="/documents/42" element={<div>Document 42</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Login page", () => {
  it("shows validation errors for empty fields", async () => {
    renderLogin(createClient({ adapter: fail(401, {}) }));
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
  });

  it("shows the backend error message, never the password, on bad credentials", async () => {
    const secretPassword = "definitely-secret-123"; // secret-scan: allow (test sentinel)
    renderLogin(
      createClient({
        adapter: fail(401, {
          error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password" },
        }),
      }),
    );
    await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), secretPassword);
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Invalid email or password");
    expect(alert.textContent).not.toContain(secretPassword);
    expect(document.body.textContent).not.toContain(secretPassword);
  });

  it("navigates to / after a successful login with no return path", async () => {
    renderLogin(
      createClient({ adapter: ok({ access_token: "tok", token_type: "bearer", user: USER }) }),
    );
    await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), "whatever123");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("Dashboard page")).toBeInTheDocument();
  });

  it("returns to the originally requested internal page after login", async () => {
    renderLogin(
      createClient({ adapter: ok({ access_token: "tok", token_type: "bearer", user: USER }) }),
      [{ pathname: "/login", state: { from: "/documents/42" } }],
    );
    await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), "whatever123");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("Document 42")).toBeInTheDocument();
  });

  it("ignores an external return path and falls back to /", async () => {
    renderLogin(
      createClient({ adapter: ok({ access_token: "tok", token_type: "bearer", user: USER }) }),
      [{ pathname: "/login", state: { from: "https://evil.com" } }],
    );
    await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), "whatever123");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("Dashboard page")).toBeInTheDocument();
  });
});
