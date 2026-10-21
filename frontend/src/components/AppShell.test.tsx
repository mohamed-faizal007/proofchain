import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Role } from "../api/types";
import { routerFuture } from "../routerFuture";
import { AppShell } from "./AppShell";

let roles: Role[] | null = null;
const logout = vi.fn();

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: roles ? { id: "u1", email: "u@x", full_name: "Una User", roles } : null,
    logout,
  }),
}));

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function renderShell() {
  render(
    <MemoryRouter future={routerFuture}>
      <AppShell>
        <p>content</p>
        <Where />
      </AppShell>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  roles = null;
  logout.mockReset();
});

describe("AppShell nav", () => {
  it("shows an Approvals link to /approvals for an approver", () => {
    roles = ["APPROVER"];
    renderShell();
    expect(screen.getByRole("link", { name: "Approvals" })).toHaveAttribute("href", "/approvals");
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
  });

  it("hides Approvals from an issuer", () => {
    roles = ["ISSUER"];
    renderShell();
    expect(screen.queryByRole("link", { name: "Approvals" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
  });

  it("hides Approvals and History when signed out", () => {
    renderShell();
    expect(screen.queryByRole("link", { name: "Approvals" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "History" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Verify a document" })).toBeInTheDocument();
  });
});

describe("AppShell user menu", () => {
  it("shows the signed-in user and roles in the sidebar", () => {
    roles = ["ISSUER", "ADMIN"];
    renderShell();
    expect(screen.getByText("Una User")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Roles" })).toHaveTextContent("ISSUERADMIN");
  });

  it("sign out clears the session through the auth context and goes to /login", () => {
    roles = ["ISSUER"];
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("where")).toHaveTextContent("/login");
  });

  it("has no sign-out control for an anonymous visitor, who gets a Sign in link", () => {
    renderShell();
    expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });
});
