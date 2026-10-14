import type { ReactElement, ReactNode } from "react";

/** A shimmering placeholder block; size it with `className` (h-*, w-*). */
export function Skeleton({ className = "" }: { className?: string }): ReactElement {
  return <div aria-hidden="true" className={`skeleton ${className}`} />;
}

/** Wraps skeleton layout so assistive tech hears one status message instead of a pile of blocks. */
export function LoadingRegion({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}): ReactElement {
  return (
    <div role="status" aria-busy="true" className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/** Skeleton rows matching a `.card` table or list: used while a list query loads. */
export function RowsSkeleton({
  label,
  rows = 4,
  className = "",
}: {
  label: string;
  rows?: number;
  className?: string;
}): ReactElement {
  return (
    <LoadingRegion label={label} className={`divide-y dark:divide-gray-700/70 ${className}`}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-5 w-16" />
          <Skeleton className="ml-auto h-4 w-20" />
        </div>
      ))}
    </LoadingRegion>
  );
}

/** Skeleton cards matching the `.card` list items (revisions, approvals). */
export function CardsSkeleton({
  label,
  count = 2,
}: {
  label: string;
  count?: number;
}): ReactElement {
  return (
    <LoadingRegion label={label} className="space-y-3">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="card space-y-3 p-5">
          <div className="flex items-center justify-between">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-5 w-16" />
          </div>
          <Skeleton className="h-3 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ))}
    </LoadingRegion>
  );
}
