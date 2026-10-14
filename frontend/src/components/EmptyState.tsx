import type { ReactElement, ReactNode } from "react";

/** "Nothing here yet": one line of explanation and, where it makes sense, the action that fills it. */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}): ReactElement {
  return (
    <div className="animate-fade-rise flex flex-col items-center px-6 py-12 text-center">
      <span
        aria-hidden="true"
        className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-600 ring-1 ring-inset ring-blue-500/25 dark:text-blue-300"
      >
        <svg
          viewBox="0 0 24 24"
          className="h-6 w-6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M7 3h7l5 5v13H7z M14 3v5h5 M10 13h6 M10 17h4" />
        </svg>
      </span>
      <p className="mt-4 font-display text-lg font-bold tracking-tight">{title}</p>
      {children && (
        <p className="mt-1 max-w-sm text-sm text-gray-500 dark:text-gray-400">{children}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
