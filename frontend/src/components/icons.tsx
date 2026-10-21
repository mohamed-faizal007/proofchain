import type { ReactElement } from "react";

/** Hand-drawn 24x24 stroke icons (no icon library, so no extra bundle weight). */
const PATHS = {
  dashboard: "M4 4h7v9H4z M13 4h7v5h-7z M13 11h7v9h-7z M4 15h7v5H4z",
  document: "M7 3h7l5 5v13H7z M14 3v5h5 M10 13h6 M10 17h4",
  plus: "M12 5v14 M5 12h14",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M9 12l2 2 4-4",
  shieldAlert: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M12 8v5 M12 16v.01",
  history: "M3 12a9 9 0 109-9 9 9 0 00-6.4 2.6L3 8 M3 3v5h5 M12 7v5l3 2",
  inbox: "M4 13l2-8h12l2 8 M4 13v6h16v-6 M4 13h5l1 2h4l1-2h5",
  check: "M5 12.5l4.5 4.5L19 7.5",
  checkCircle: "M8 12.5l2.7 2.7L16 9.5 M12 21a9 9 0 100-18 9 9 0 000 18z",
  x: "M6 6l12 12 M18 6L6 18",
  xCircle: "M9 9l6 6 M15 9l-6 6 M12 21a9 9 0 100-18 9 9 0 000 18z",
  alert: "M12 9v4 M12 17v.01 M10.3 4l-8 14a2 2 0 001.7 3h16a2 2 0 001.7-3l-8-14a2 2 0 00-3.4 0z",
  help: "M9.5 9a2.5 2.5 0 115 0c0 1.7-2.5 2-2.5 4 M12 17v.01 M12 21a9 9 0 100-18 9 9 0 000 18z",
  clock: "M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z",
  link: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1 M14 10a4 4 0 00-5.7 0l-3 3A4 4 0 0011 18.7l1-1",
  cube: "M12 3l8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5 M12 12v9 M12 12L4 7.5",
  hash: "M5 9h14 M5 15h14 M10 4L8 20 M16 4l-2 16",
  upload: "M12 16V5 M7.5 9.5L12 5l4.5 4.5 M5 15v4h14v-4",
  download: "M12 4v11 M7.5 10.5L12 15l4.5-4.5 M5 19h14",
  copy: "M9 9h10v11H9z M5 15V4h10",
  external: "M14 4h6v6 M20 4l-9 9 M18 14v6H4V6h6",
  logout: "M9 4H5v16h4 M16 8l4 4-4 4 M20 12H9",
  sun: "M12 16a4 4 0 100-8 4 4 0 000 8z M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5.6 5.6L7 7 M17 17l1.4 1.4 M5.6 18.4L7 17 M17 7l1.4-1.4",
  moon: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
  menu: "M4 7h16 M4 12h16 M4 17h16",
  chevronRight: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  arrowRight: "M5 12h14 M13 6l6 6-6 6",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14z M20 20l-4-4",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8z M4 21a8 8 0 0116 0",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5 M3 17.5l9 5 9-5",
  fingerprint:
    "M6 18c0-1 .5-2 .5-4a5.5 5.5 0 0111 0c0 3 0 5-1 7 M9 20c.5-2 .5-4 .5-6a2.5 2.5 0 015 0c0 2.5 0 4.5-.5 6 M4 12a8 8 0 0116 0 M12 12v3",
  edit: "M4 20h4L19 9a2.8 2.8 0 00-4-4L4 16z M14 6l4 4",
  trash: "M5 7h14 M10 11v6 M14 11v6 M6 7l1 13h10l1-13 M9 7V4h6v3",
  refresh: "M20 11a8 8 0 00-14.5-3.5L4 9 M4 4v5h5 M4 13a8 8 0 0014.5 3.5L20 15 M20 20v-5h-5",
  file: "M7 3h7l5 5v13H7z M14 3v5h5",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z",
  lock: "M6 11h12v9H6z M8 11V8a4 4 0 018 0v3",
  globe:
    "M12 21a9 9 0 100-18 9 9 0 000 18z M3 12h18 M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9S9.5 5.5 12 3z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  className = "h-5 w-5",
  strokeWidth = 1.8,
}: {
  name: IconName;
  className?: string;
  strokeWidth?: number;
}): ReactElement {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

/** The brand mark: a rounded gradient tile holding a checked shield. */
export function BrandMark({ className = "h-9 w-9" }: { className?: string }): ReactElement {
  return (
    <span
      aria-hidden="true"
      className={`bg-brand flex shrink-0 items-center justify-center rounded-xl text-white shadow-glow ${className}`}
    >
      <Icon name="shield" className="h-[58%] w-[58%]" strokeWidth={2} />
    </span>
  );
}
