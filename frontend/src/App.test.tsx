import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "./App";
import { routerFuture } from "./routerFuture";

function renderApp(entries: string[]) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter future={routerFuture} initialEntries={entries}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const publicRoutes: [string, string][] = [
  ["/login", "Login"],
  ["/register", "Register"],
  ["/verify", "Verify"],
];

describe("public routes", () => {
  it.each(publicRoutes)("%s renders without a session", async (path, heading) => {
    renderApp([path]);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it("renders NotFound for an unknown path", () => {
    renderApp(["/nope"]);
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });
});

const protectedRoutes: string[] = [
  "/",
  "/documents/new",
  "/documents/abc",
  "/documents/abc/revisions/new",
  "/approvals",
  "/verifications",
  "/verifications/v1",
];

describe("protected routes without a session", () => {
  it.each(protectedRoutes)("%s redirects to /login", async (path) => {
    renderApp([path]);
    expect(await screen.findByRole("heading", { level: 1, name: "Login" })).toBeInTheDocument();
  });
});
