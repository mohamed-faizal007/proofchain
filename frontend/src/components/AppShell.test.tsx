import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Role } from "../api/types";
import { routerFuture } from "../routerFuture";
import { AppShell } from "./AppShell";

let roles: Role[] | null = null;

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: roles ? { id: "u1", email: "u@x", full_name: "U", roles } : null }),
}));

function renderShell() {
  render(
    <MemoryRouter future={routerFuture}>
      <AppShell>
        <p>content</p>
      </AppShell>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  roles = null;
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
