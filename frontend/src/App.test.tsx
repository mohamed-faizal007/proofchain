import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "./App";
import { routerFuture } from "./routerFuture";

const publicRoutes: [string, string][] = [
  ["/login", "Login"],
  ["/register", "Register"],
  ["/verify", "Verify"],
];

describe("public routes", () => {
  it.each(publicRoutes)("%s renders without a session", async (path, heading) => {
    render(
      <MemoryRouter future={routerFuture} initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it("renders NotFound for an unknown path", () => {
    render(
      <MemoryRouter future={routerFuture} initialEntries={["/nope"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
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
    render(
      <MemoryRouter future={routerFuture} initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Login" })).toBeInTheDocument();
  });
});
