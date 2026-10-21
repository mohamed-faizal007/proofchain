import type { ReactElement } from "react";
import type { StepStatus, VerificationStep } from "../api/types";
import { Icon, type IconName } from "./icons";

const STEP_LABELS: Record<string, string> = {
  FILE_HASH: "File hash",
  TEXT_ROOT: "Text Merkle root",
  LOCALIZATION: "Change localization",
  AUTHORIZATION: "Authorization",
  CHAIN_CHECK: "Chain check",
  SEMANTIC_ANALYSIS: "Semantic analysis",
};

const STATUS_STYLES: Record<
  StepStatus,
  { text: string; icon: IconName; node: string; chip: string; line: string }
> = {
  PASS: {
    text: "Pass",
    icon: "check",
    node: "bg-green-500 text-white shadow-[0_0_14px_rgb(34_197_94/0.45)]",
    chip: "badge-green",
    line: "bg-green-500/60",
  },
  FAIL: {
    text: "Fail",
    icon: "x",
    node: "bg-red-500 text-white shadow-[0_0_14px_rgb(239_68_68/0.5)]",
    chip: "badge-red",
    line: "bg-red-500/60",
  },
  WARN: {
    text: "Warning",
    icon: "alert",
    node: "bg-amber-500 text-white shadow-[0_0_14px_rgb(245_158_11/0.45)]",
    chip: "badge-amber",
    line: "bg-amber-500/60",
  },
  DONE: {
    text: "Done",
    icon: "check",
    node: "bg-blue-500 text-white",
    chip: "badge-accent",
    line: "bg-blue-500/50",
  },
  SKIPPED: {
    text: "Skipped",
    icon: "chevronRight",
    node: "bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-300",
    chip: "badge-grey",
    line: "bg-gray-300 dark:bg-gray-700",
  },
};

/** The server's step order is the pipeline order (file hash → … → semantic); shown as sent.
 * A horizontal stepper from `lg` up, a vertical one below. */
export function PipelineSteps({ steps }: { steps: VerificationStep[] }): ReactElement {
  return (
    <ol
      aria-label="Verification pipeline"
      className="stagger lg:grid lg:auto-cols-fr lg:grid-flow-col lg:gap-4"
    >
      {steps.map((step, i) => {
        const style = STATUS_STYLES[step.status] ?? STATUS_STYLES.SKIPPED;
        const last = i === steps.length - 1;
        return (
          <li
            key={step.name}
            data-step={step.name}
            className="relative flex gap-3.5 pb-5 text-sm last:pb-0 lg:block lg:pb-0"
          >
            {!last && (
              <span
                aria-hidden="true"
                className={`absolute bottom-0 left-[0.95rem] top-9 w-px lg:bottom-auto lg:left-11 lg:right-[-1rem] lg:top-[0.95rem] lg:h-px lg:w-auto ${style.line}`}
              />
            )}
            <span
              aria-hidden="true"
              className={`relative z-[1] flex h-[1.9rem] w-[1.9rem] shrink-0 items-center justify-center rounded-full ${style.node}`}
            >
              <Icon name={style.icon} className="h-4 w-4" strokeWidth={2.6} />
            </span>
            <div className="min-w-0 lg:mt-3">
              <p className="font-semibold">{STEP_LABELS[step.name] ?? step.name}</p>
              <span className={`badge ${style.chip} mt-1 !px-2 !py-px !text-[11px]`}>
                {style.text}
              </span>
              {step.detail && (
                <span className="mt-1.5 block text-xs leading-relaxed text-gray-600 dark:text-gray-400">
                  {step.detail}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
