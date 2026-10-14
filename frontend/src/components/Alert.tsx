import type { ReactElement, ReactNode } from "react";

type AlertVariant = "error" | "success" | "info";

const PATHS: Record<AlertVariant, string> = {
  error: "M12 8v5 M12 16.5v.01 M12 21a9 9 0 100-18 9 9 0 000 18z",
  success: "M8 12.5l2.7 2.7L16 9.5 M12 21a9 9 0 100-18 9 9 0 000 18z",
  info: "M12 11v5 M12 7.5v.01 M12 21a9 9 0 100-18 9 9 0 000 18z",
};

/** The one message style for errors (role=alert, shows the API message), success and info
 * (role=status). Animates in; callers keep their own spacing via `className`. */
export function Alert({
  variant = "error",
  className = "",
  live = true,
  children,
}: {
  variant?: AlertVariant;
  className?: string;
  /** false for persistent state shown on load (not announced as an event). */
  live?: boolean;
  children: ReactNode;
}): ReactElement {
  return (
    <div
      role={live ? (variant === "error" ? "alert" : "status") : undefined}
      className={`alert alert-${variant} animate-fade-rise ${className}`}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="mt-px h-4 w-4 shrink-0"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={PATHS[variant]} />
      </svg>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
