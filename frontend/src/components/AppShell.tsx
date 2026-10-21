import type { ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { getStoredToken } from "../auth/storage";
import { Breadcrumbs } from "./Breadcrumbs";
import { BrandMark, Icon } from "./icons";
import { SidebarNav } from "./SidebarNav";
import { ThemeToggle } from "./ThemeToggle";
import { ToastProvider } from "./Toast";
import { UserCard } from "./UserCard";

function Brand(): ReactElement {
  return (
    <Link
      to="/"
      className="flex items-center gap-2.5 font-display text-xl font-bold tracking-tight"
    >
      <BrandMark />
      <span>
        Proof<span className="text-brand">Chain</span>
      </span>
    </Link>
  );
}

function PublicBar(): ReactElement {
  return (
    <header className="sticky top-0 z-20 border-b border-gray-200/80 bg-white/75 backdrop-blur-md dark:border-gray-700/60 dark:bg-gray-950/70">
      <div className="mx-auto flex max-w-[88rem] items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Brand />
        <nav aria-label="Main" className="flex items-center gap-2 text-sm">
          <Link to="/verify" className="nav-item" aria-current="page">
            Verify a document
          </Link>
          <Link to="/login" className="btn-secondary">
            Sign in
          </Link>
          <ThemeToggle className="hidden sm:inline-flex" />
        </nav>
      </div>
    </header>
  );
}

/** Login/Register own their whole screen; Verify is public, so anonymous visitors get a slim bar.
 * The page content keeps one fixed position in the tree across all three layouts, so it is not
 * remounted (and a half-filled form is not lost) when the auth state settles. */
export function AppShell({ children }: { children: ReactNode }): ReactElement {
  const { user, isLoading } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);

  const bare = pathname === "/login" || pathname === "/register";
  // While a stored token is being validated keep the app chrome, so there is no layout flash.
  const signedIn = !!user || (!!isLoading && !!getStoredToken());
  const sidebar = !bare && signedIn;

  return (
    <ToastProvider>
      {bare && (
        <div className="absolute right-4 top-4 z-10">
          <ThemeToggle />
        </div>
      )}
      {!bare && !signedIn && <PublicBar />}
      {sidebar && (
        <>
          {open && (
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-30 bg-gray-950/60 backdrop-blur-sm lg:hidden"
            />
          )}
          <aside
            className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col gap-6 border-r border-gray-200/80 bg-gray-50/95 p-3 pt-5 backdrop-blur-xl transition-transform duration-200 dark:border-gray-700/60 dark:bg-gray-950/95 lg:translate-x-0 ${
              open ? "translate-x-0" : "-translate-x-full max-lg:invisible"
            }`}
          >
            <div className="px-1.5">
              <Brand />
            </div>
            <div className="flex-1 overflow-y-auto">
              <p className="eyebrow mb-2 px-3 !text-[10px]">Workspace</p>
              <SidebarNav />
            </div>
            <div className="space-y-3">
              {user && <UserCard user={user} />}
              <ThemeToggle className="w-full justify-center" />
            </div>
          </aside>
        </>
      )}
      <div className={sidebar ? "lg:pl-64" : undefined}>
        {sidebar && (
          <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-gray-200/80 bg-white/75 px-4 py-3 backdrop-blur-md sm:px-6 dark:border-gray-700/60 dark:bg-gray-950/70">
            <button
              type="button"
              aria-label="Open menu"
              onClick={() => setOpen(true)}
              className="-ml-1 flex h-9 w-9 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100 lg:hidden dark:text-gray-300 dark:hover:bg-gray-800"
            >
              <Icon name="menu" />
            </button>
            <div className="lg:hidden">
              <BrandMark className="h-8 w-8" />
            </div>
            <Breadcrumbs />
          </header>
        )}
        {/* Keyed by path so each route change replays the short fade-and-rise. */}
        <div key={pathname} className="animate-page-in">
          {children}
        </div>
      </div>
    </ToastProvider>
  );
}
