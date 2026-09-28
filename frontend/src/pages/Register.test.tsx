import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createClient } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { routerFuture } from "../routerFuture";
import { Register } from "./Register";

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

function renderRegister(client: AxiosInstance) {
  return render(
    <MemoryRouter future={routerFuture} initialEntries={["/register"]}>
      <AuthProvider client={client}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText(/full name/i), "New User");
  await userEvent.type(screen.getByLabelText(/email/i), "new@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "a-strong-password");
  await userEvent.click(screen.getByRole("button", { name: /create account/i }));
}

describe("Register page", () => {
  it("shows validation errors for empty fields", async () => {
    renderRegister(createClient({ adapter: fail(401, {}) }));
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/full name is required/i)).toBeInTheDocument();
    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
  });

  it("shows a success message after registering (dev, public)", async () => {
    renderRegister(
      createClient({
        adapter: ok({
          id: "u2",
          email: "new@example.com",
          full_name: "New User",
          roles: ["VERIFIER"],
          is_active: true,
          created_at: "2024-01-01T00:00:00Z",
        }),
      }),
    );
    await fillAndSubmit();
    expect(await screen.findByText(/account created/i)).toBeInTheDocument();
  });

  it("shows a clear restricted message on 403 (prod requires ADMIN)", async () => {
    renderRegister(
      createClient({ adapter: fail(403, { error: { code: "FORBIDDEN", message: "Admin only" } }) }),
    );
    await fillAndSubmit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/restricted/i);
  });

  it("shows a clear restricted message on 401 (unauthenticated in prod)", async () => {
    renderRegister(
      createClient({
        adapter: fail(401, { error: { code: "AUTH_REQUIRED", message: "Sign in" } }),
      }),
    );
    await fillAndSubmit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/restricted/i);
  });
});
