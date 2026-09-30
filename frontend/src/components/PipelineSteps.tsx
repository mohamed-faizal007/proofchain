import type { ReactElement } from "react";
import type { StepStatus, VerificationStep } from "../api/types";

const STEP_LABELS: Record<string, string> = {
  FILE_HASH: "File hash",
  TEXT_ROOT: "Text Merkle root",
  LOCALIZATION: "Change localization",
  AUTHORIZATION: "Authorization",
  CHAIN_CHECK: "Chain check",
  SEMANTIC_ANALYSIS: "Semantic analysis",
};

const STATUS_STYLES: Record<StepStatus, { text: string; symbol: string; cls: string }> = {
  PASS: { text: "Pass", symbol: "✓", cls: "bg-green-100 text-green-900" },
  FAIL: { text: "Fail", symbol: "✗", cls: "bg-red-100 text-red-900" },
  WARN: { text: "Warning", symbol: "!", cls: "bg-amber-100 text-amber-900" },
  DONE: { text: "Done", symbol: "•", cls: "bg-blue-100 text-blue-900" },
  SKIPPED: { text: "Skipped", symbol: "–", cls: "bg-gray-100 text-gray-700" },
};

/** The server's step order is the pipeline order (file hash → … → semantic); shown as sent. */
export function PipelineSteps({ steps }: { steps: VerificationStep[] }): ReactElement {
  return (
    <ol aria-label="Verification pipeline" className="space-y-2">
      {steps.map((step) => {
        const style = STATUS_STYLES[step.status] ?? STATUS_STYLES.SKIPPED;
        return (
          <li key={step.name} data-step={step.name} className="flex items-start gap-3 text-sm">
            <span className={`mt-0.5 rounded px-2 py-0.5 text-xs font-semibold ${style.cls}`}>
              <span aria-hidden="true">{style.symbol} </span>
              {style.text}
            </span>
            <span>
              <span className="font-medium">{STEP_LABELS[step.name] ?? step.name}</span>
              {step.detail && <span className="block text-gray-600">{step.detail}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
