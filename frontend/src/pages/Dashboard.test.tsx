import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { routerFuture } from "../routerFuture";
import { Dashboard } from "./Dashboard";

function jsonResponse(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: "OK", headers: {}, config } as AxiosResponse;
}

/** Routes /documents (by page_size) and /verifications; records every /documents list-query call. */
function makeAdapter(listCalls: Record<string, unknown>[]): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) => {
    const params = (config.params ?? {}) as Record<string, unknown>;
    if (config.url === "/documents") {
      if (params.page_size === 20) {
        listCalls.push(params);
        return Promise.resolve(
          jsonResponse(config, { items: [], page: params.page ?? 1, page_size: 20, total: 0 }),
        );
      }
      if (params.status === "PENDING") {
        return Promise.resolve(
          jsonResponse(config, { items: [], page: 1, page_size: 1, total: 2 }),
        );
      }
      return Promise.resolve(jsonResponse(config, { items: [], page: 1, page_size: 1, total: 10 }));
    }
    if (config.url === "/verifications") {
      return Promise.resolve(jsonResponse(config, { items: [], page: 1, page_size: 5, total: 0 }));
    }
    return Promise.reject(new Error(`unexpected url ${config.url}`));
  };
}

function renderDashboard(initialEntries: string[] = ["/"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture} initialEntries={initialEntries}>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Dashboard />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Dashboard", () => {
  it("renders counts and an empty document table", async () => {
    api.defaults.adapter = makeAdapter([]);
    renderDashboard();

    expect(await screen.findByText("10")).toBeInTheDocument(); // Documents
    expect(await screen.findByText("2")).toBeInTheDocument(); // pending
    expect(await screen.findByText(/no verifications yet/i)).toBeInTheDocument();
    expect(await screen.findByText(/no documents match these filters/i)).toBeInTheDocument();
  });

  it("shows a per-section error without hiding the rest of the page", async () => {
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      const params = (config.params ?? {}) as Record<string, unknown>;
      if (config.url === "/documents" && params.status === "PENDING") {
        return Promise.reject(new Error("boom"));
      }
      if (config.url === "/documents") {
        return Promise.resolve(
          jsonResponse(config, {
            items: [],
            page: 1,
            page_size: (params.page_size as number) ?? 20,
            total: params.page_size === 1 ? 10 : 0,
          }),
        );
      }
      if (config.url === "/verifications") {
        return Promise.resolve(
          jsonResponse(config, { items: [], page: 1, page_size: 5, total: 0 }),
        );
      }
      return Promise.reject(new Error("unexpected"));
    }) as AxiosAdapter;

    renderDashboard();

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(await screen.findByText("10")).toBeInTheDocument();
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/search documents/i)).toBeInTheDocument();
  });

  it("debounces rapid search input into a single request carrying the final value", async () => {
    const listCalls: Record<string, unknown>[] = [];
    api.defaults.adapter = makeAdapter(listCalls);
    renderDashboard();

    const input = await screen.findByLabelText(/search documents/i);
    await waitFor(() => expect(listCalls.length).toBeGreaterThan(0));
    const callsBeforeTyping = listCalls.length;

    fireEvent.change(input, { target: { value: "l" } });
    fireEvent.change(input, { target: { value: "le" } });
    fireEvent.change(input, { target: { value: "lease" } });

    // Still within the debounce window: no extra request yet.
    expect(listCalls.length).toBe(callsBeforeTyping);

    await waitFor(
      () => {
        const last = listCalls.at(-1) as { q?: string } | undefined;
        expect(last?.q).toBe("lease");
      },
      { timeout: 2000 },
    );
    expect(listCalls.length).toBe(callsBeforeTyping + 1);
    const last = listCalls.at(-1) as { page?: number };
    expect(last.page).toBe(1);
  });

  it("resets the page to 1 when a filter changes", async () => {
    const listCalls: Record<string, unknown>[] = [];
    api.defaults.adapter = makeAdapter(listCalls);
    renderDashboard(["/?page=3"]);

    const statusSelect = await screen.findByLabelText(/filter by status/i);
    fireEvent.change(statusSelect, { target: { value: "PENDING" } });

    await waitFor(() => {
      const last = listCalls.at(-1) as { status?: string; page?: number } | undefined;
      expect(last?.status).toBe("PENDING");
    });
    const last = listCalls.at(-1) as { page?: number };
    expect(last.page).toBe(1);
  });
});
