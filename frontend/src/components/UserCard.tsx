import type { ReactElement } from "react";
import { useNavigate } from "react-router-dom";
import type { User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "./icons";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "?";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/** Signed-in user, their roles, and sign-out. Sign-out only clears the session (AuthContext.logout)
 * and goes to /login. */
export function UserCard({ user }: { user: User }): ReactElement {
  const { logout } = useAuth();
  const navigate = useNavigate();

  function signOut(): void {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="rounded-2xl border border-gray-200/80 bg-white/60 p-3 dark:border-gray-700/60 dark:bg-gray-800/40">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="bg-brand flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
        >
          {initials(user.full_name)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{user.full_name}</p>
          <p className="truncate text-xs text-gray-500 dark:text-gray-400">{user.email}</p>
        </div>
      </div>
      <ul aria-label="Roles" className="mt-2.5 flex flex-wrap gap-1">
        {user.roles.map((role) => (
          <li key={role} className="badge badge-accent !px-2 !py-px !text-[10px] tracking-wider">
            {role}
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={signOut}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700 dark:border-gray-700 dark:text-gray-300 dark:hover:border-red-500/40 dark:hover:bg-red-500/10 dark:hover:text-red-300"
      >
        <Icon name="logout" className="h-4 w-4" />
        Sign out
      </button>
    </div>
  );
}
