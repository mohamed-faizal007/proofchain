import type { ReactElement } from "react";
import { useEffect, useRef, useState } from "react";

const COPIED_MESSAGE_MS = 1500;

/** Copies `value` and confirms it: the icon flips to a green check and "copied" appears. */
export function CopyButton({ value, label }: { value: string; label: string }): ReactElement {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function handleCopy(): Promise<void> {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), COPIED_MESSAGE_MS);
    } catch {
      // Clipboard write denied/unavailable: no crash, no confirmation shown.
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => void handleCopy()}
        aria-label={label}
        className={`inline-flex h-5 w-5 items-center justify-center rounded transition-colors ${
          copied
            ? "text-green-600 dark:text-green-400"
            : "text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200"
        }`}
      >
        <svg
          key={copied ? "done" : "copy"}
          aria-hidden="true"
          viewBox="0 0 24 24"
          className={`h-3.5 w-3.5 ${copied ? "animate-check-pop" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {copied ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M9 9h10v11H9z M5 15V4h10" />}
        </svg>
      </button>
      {copied && (
        <span role="status" className="animate-fade-rise text-green-600 dark:text-green-400">
          copied
        </span>
      )}
    </>
  );
}
