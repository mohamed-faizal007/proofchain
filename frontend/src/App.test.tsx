import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "./App";
import { routerFuture } from "./routerFuture";

const routes: [string, string][] = [
  ["/login", "Login"],
  ["/register", "Register"],
  ["/", "Dashboard"],
  ["/documents/new", "New document"],
  ["/documents/abc", "Document"],
  ["/documents/abc/revisions/new", "New revision"],
  ["/approvals", "Approvals"],
  ["/verify", "Verify"],
  ["/verifications", "Verification history"],
  ["/verifications/v1", "Verification"],
];

describe("routes", () => {
  it.each(routes)("%s renders its placeholder heading", (path, heading) => {
    render(
      <MemoryRouter future={routerFuture} initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
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
