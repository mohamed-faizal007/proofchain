import type { ReactElement, ReactNode } from "react";
import { Icon, type IconName } from "./icons";

/** Title block for form and list pages: icon tile, h1, one line of context, optional actions. */
export function PageHeader({
  icon,
  title,
  children,
  actions,
}: {
  icon: IconName;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}): ReactElement {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-4">
        <span
          aria-hidden="true"
          className="bg-brand hidden h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-white shadow-glow sm:flex"
        >
          <Icon name={icon} className="h-6 w-6" />
        </span>
        <div className="min-w-0">
          <h1 className="page-title">{title}</h1>
          {children && (
            <p className="mt-1.5 max-w-2xl text-sm text-gray-600 dark:text-gray-400">{children}</p>
          )}
        </div>
      </div>
      {actions}
    </header>
  );
}
