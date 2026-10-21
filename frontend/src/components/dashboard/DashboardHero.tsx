import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";
import type { User } from "../../api/types";
import { RoleGate } from "../../auth/RoleGate";
import { Icon } from "../icons";

function greeting(now: Date): string {
  const h = now.getHours();
  if (h < 5) return "Working late";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

/** Decorative: three linked blocks around a shield, the "chain of proof" in one picture. */
function ChainArt(): ReactElement {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 320 160"
      className="h-full w-full"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <defs>
        <linearGradient id="hero-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#b3a7ff" />
          <stop offset="1" stopColor="#5b8cff" />
        </linearGradient>
      </defs>
      <g stroke="url(#hero-g)" strokeWidth="2">
        <path d="M92 80h40M188 80h40" strokeDasharray="3 6" opacity="0.8" />
        <rect x="24" y="48" width="68" height="64" rx="14" opacity="0.55" />
        <rect x="228" y="48" width="68" height="64" rx="14" opacity="0.55" />
        <rect x="132" y="36" width="56" height="88" rx="16" fill="rgb(125 104 251 / 0.14)" />
        <path d="M160 58l16 6v14c0 10-7 17-16 19-9-2-16-9-16-19V64z" />
        <path d="M153 80l5 5 9-10" strokeWidth="2.4" />
        <path d="M44 72h28M44 88h18M248 72h28M248 88h18" opacity="0.6" />
      </g>
    </svg>
  );
}

export function DashboardHero({
  user,
  summary,
  children,
}: {
  user: User;
  /** One line: what the system is holding right now. */
  summary: ReactNode;
  children?: ReactNode;
}): ReactElement {
  const first = user.full_name.trim().split(/\s+/)[0] ?? user.full_name;
  return (
    <section aria-label="Overview" className="hero animate-fade-rise p-6 sm:p-8">
      <div className="relative flex flex-wrap items-center justify-between gap-6">
        <div className="min-w-0 max-w-xl">
          <ul aria-label="Your roles" className="flex flex-wrap gap-1.5">
            {user.roles.map((role) => (
              <li key={role} className="badge badge-accent !text-[11px] tracking-wider">
                {role}
              </li>
            ))}
          </ul>
          <p className="page-title mt-3">
            {greeting(new Date())}, <span className="text-brand">{first}</span>
          </p>
          <p className="mt-2 text-base text-gray-600 dark:text-gray-300">{summary}</p>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <RoleGate roles={["ISSUER"]}>
              <Link to="/documents/new" className="btn-primary px-5 py-2.5">
                <Icon name="plus" className="h-4 w-4" strokeWidth={2.4} />
                New document
              </Link>
            </RoleGate>
            <Link to="/verify" className="btn-secondary px-4 py-2.5">
              <Icon name="shield" className="h-4 w-4" />
              Verify a document
            </Link>
            <RoleGate roles={["APPROVER"]}>
              <Link to="/approvals" className="btn-secondary px-4 py-2.5">
                <Icon name="inbox" className="h-4 w-4" />
                Review approvals
              </Link>
            </RoleGate>
            {children}
          </div>
        </div>
        <div className="hidden h-36 w-72 shrink-0 md:block xl:w-80">
          <ChainArt />
        </div>
      </div>
    </section>
  );
}
