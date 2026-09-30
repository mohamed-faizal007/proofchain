import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { AppRoutes } from "../App";
import { api } from "../api/client";
import { routerFuture } from "../routerFuture";
import { makeReport } from "../test/verificationFixtures";
import { getStoredToken, setStoredToken } from "./storage";

// pdf.js is not under test here; the candidate viewer just needs something to open.
const openPdf = vi.hoisted(() => vi.fn());
vi.mock("../lib/pdfjs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/pdfjs")>()),
  openPdf,
}));

const reply = (config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse => ({
  data,
  status,
  statusText: "",
  headers: {},
  config,
});

const unauthorized = (config: InternalAxiosRequestConfig) =>
  Promise.reject(
    new AxiosError(
      "failed",
      "ERR_BAD_REQUEST",
      config,
      null,
      reply(config, { error: { code: "AUTH_REQUIRED", message: "Token expired" } }, 401),
    ),
  );

let requests: string[] = [];
let verifyResponse: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;

function LocationProbe() {
  return <p data-testid="path">{useLocation().pathname}</p>;
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter future={routerFuture} initialEntries={[path]}>
        <AppRoutes />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  requests = [];
  // Every authenticated call fails as it would with an expired JWT: the server 401s the bearer
  // token on /auth/me, and (PUBLIC_VERIFY=false) on /verify.
  api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
    const url = String(config.url);
    requests.push(url);
    if (url === "/verify") return verifyResponse(config);
    return unauthorized(config);
  }) as AxiosAdapter;
  verifyResponse = (config) => Promise.resolve(reply(config, makeReport()));
  openPdf.mockReset();
  openPdf.mockImplementation(async () => ({
    numPages: 1,
    getPage: () =>
      Promise.resolve({
        rotate: 0,
        getViewport: ({ scale }: { scale: number }) => ({
          width: 600 * scale,
          height: 800 * scale,
        }),
        render: () => ({ promise: new Promise(() => {}), cancel: vi.fn() }),
      }),
    destroy: () => Promise.resolve(),
  }));
  vi.stubGlobal("IntersectionObserver", undefined);
  setStoredToken("expired-jwt");
});
afterEach(() => vi.unstubAllGlobals());

const pdf = () => new File(["CAND"], "upload.pdf", { type: "application/pdf" });

describe("public routes with an expired token in storage", () => {
  it("/verify: no redirect to /login, token dropped silently, anonymous verify still works", async () => {
    renderAt("/verify");
    expect(await screen.findByRole("heading", { level: 1, name: "Verify" })).toBeInTheDocument();
    await waitFor(() => expect(requests).toContain("/auth/me"));
    await waitFor(() => expect(getStoredToken()).toBeNull());
    expect(screen.getByTestId("path")).toHaveTextContent("/verify");

    await userEvent.upload(await screen.findByLabelText("Choose PDF file"), pdf());
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    expect(await screen.findByRole("region", { name: "Verdict" })).toBeInTheDocument();
    expect(screen.getByTestId("path")).toHaveTextContent("/verify");
  });

  it("/verify: a 401 from POST /verify itself shows a message instead of redirecting", async () => {
    verifyResponse = unauthorized;
    renderAt("/verify");
    fireEvent.change(await screen.findByLabelText("Choose PDF file"), {
      target: { files: [pdf()] },
    });
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    expect(await screen.findByText("Sign in to verify documents.")).toBeInTheDocument();
    expect(screen.getByTestId("path")).toHaveTextContent("/verify");
    expect(screen.getByRole("heading", { level: 1, name: "Verify" })).toBeInTheDocument();
  });

  it("/register: no redirect to /login", async () => {
    renderAt("/register");
    expect(await screen.findByRole("heading", { level: 1, name: "Register" })).toBeInTheDocument();
    await waitFor(() => expect(requests).toContain("/auth/me"));
    await waitFor(() => expect(getStoredToken()).toBeNull());
    expect(screen.getByTestId("path")).toHaveTextContent("/register");
  });

  it("a protected route still sends the same visitor to /login", async () => {
    renderAt("/approvals");
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/login"));
  });
});
