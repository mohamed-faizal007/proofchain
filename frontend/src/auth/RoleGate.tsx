import type { ReactElement, ReactNode } from "react";
import type { Role } from "../api/types";
import { useAuth } from "./AuthContext";

/** Hides children when the signed-in user lacks every listed role. UX only, never a security boundary. */
export function RoleGate({
  roles,
  children,
}: {
  roles: Role[];
  children: ReactNode;
}): ReactElement | null {
  const { user } = useAuth();
  if (!user || !roles.some((role) => user.roles.includes(role))) return null;
  return <>{children}</>;
}
