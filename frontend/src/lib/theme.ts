export type Theme = "light" | "dark";

/** Shared with the inline script in index.html, which must stay in step with this file. */
export const THEME_KEY = "proofchain.theme";

function stored(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch {
    return null;
  }
}

/** Used when nothing is stored. Deliberately NOT the OS preference, so a demo looks the same on any machine. */
export const DEFAULT_THEME: Theme = "dark";

export function resolveTheme(): Theme {
  return stored() ?? DEFAULT_THEME;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // storage blocked: the choice only lasts for this page view
  }
}

/** Idempotent; index.html has normally applied the same theme before React mounts. */
export function initTheme(): void {
  applyTheme(resolveTheme());
}
