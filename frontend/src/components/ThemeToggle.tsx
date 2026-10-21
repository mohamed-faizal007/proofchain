import type { ReactElement } from "react";
import { useState } from "react";
import { applyTheme, saveTheme, type Theme } from "../lib/theme";
import { Icon } from "./icons";

function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function ThemeToggle({ className = "" }: { className?: string }): ReactElement {
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
      className={`inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:border-gray-600 ${className}`}
    >
      <Icon
        name={dark ? "moon" : "sun"}
        className={`h-4 w-4 ${dark ? "text-blue-300" : "text-amber-500"}`}
      />
      <span>{dark ? "Dark mode: on" : "Dark mode: off"}</span>
    </button>
  );
}
