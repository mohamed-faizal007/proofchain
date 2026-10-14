import type { ReactElement } from "react";

/** Inline "working" indicator for buttons. Decorative: the button label carries the meaning. */
export function Spinner(): ReactElement {
  return <span aria-hidden="true" className="spinner" />;
}
