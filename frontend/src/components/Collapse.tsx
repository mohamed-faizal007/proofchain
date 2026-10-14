import type { ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";
import { prefersReducedMotion } from "../lib/motion";

const EXIT_MS = 180;

/** Animates children open and closed (grid rows 0fr/1fr) and unmounts them once closed, so hidden
 * controls never stay in the tab order. With reduced motion (or no matchMedia) it simply
 * mounts and unmounts. */
export function Collapse({
  open,
  children,
}: {
  open: boolean;
  children: ReactNode;
}): ReactElement | null {
  const [mounted, setMounted] = useState(open);

  useEffect(() => {
    if (open) {
      setMounted(true);
      return;
    }
    if (prefersReducedMotion()) {
      setMounted(false);
      return;
    }
    const id = window.setTimeout(() => setMounted(false), EXIT_MS);
    return () => window.clearTimeout(id);
  }, [open]);

  if (!open && (!mounted || prefersReducedMotion())) return null;
  return (
    <div
      className={`grid ${open ? "animate-collapse-open" : "animate-collapse-close"}`}
      style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
    >
      {/* -m-1 p-1 keeps focus rings from being clipped by overflow-hidden */}
      <div className="-m-1 min-h-0 overflow-hidden p-1">{children}</div>
    </div>
  );
}
