/** True when the user asked for reduced motion. Also true where `matchMedia` is missing (jsdom),
 * so JS-timed exits (Collapse, toasts) unmount immediately instead of waiting for an animation. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
