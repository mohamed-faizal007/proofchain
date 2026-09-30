import type { ReactElement } from "react";
import { useState } from "react";
import { applyTheme, saveTheme, type Theme } from "../lib/theme";

function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function ThemeToggle(): ReactElement {
  // Read from <html>: the blocking script in index.html already applied the resolved theme.
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const dark = theme === "dark";

  function toggle(): void {
    const next: Theme = dark ? "light" : "dark";
    applyTheme(next);
    saveTheme(next);
    setTheme(next);
  }

  return (
    <button
      type="button"
      aria-pressed={dark}
      onClick={toggle}
      className="rounded border px-2 py-1 text-xs dark:border-gray-600"
    >
      {dark ? "Dark mode: on" : "Dark mode: off"}
    </button>
  );
}
