import { render, screen } from "@testing-library/react";
import type { StepStatus, Verdict } from "../api/types";
import { CHAIN_OK, makeReport, REFERENCE } from "../test/verificationFixtures";
import { ChainProofPanel } from "./ChainProofPanel";
import { PipelineSteps } from "./PipelineSteps";
import { VerdictBanner } from "./VerdictBanner";

describe("VerdictBanner", () => {
  const cases: [Verdict, string][] = [
    ["AUTHENTIC_LATEST", "green"],
    ["AUTHENTIC_SUPERSEDED", "amber"],
    ["CONTENT_EQUIVALENT", "amber"],
    ["UNAUTHORIZED_VERSION", "red"],
    ["TAMPERED", "red"],
    ["RECORD_MISMATCH", "red"],
    ["UNKNOWN_DOCUMENT", "grey"],
  ];
  it.each(cases)("%s is %s, with a text label and the summary", (verdict, tone) => {
    render(<VerdictBanner verdict={verdict} summary="Some summary" />);
    const banner = screen.getByRole("region", { name: "Verdict" });
    expect(banner).toHaveAttribute("data-tone", tone);
    expect(banner).toHaveTextContent("Some summary");
    expect(banner.querySelector("h2")?.textContent?.length).toBeGreaterThan(3);
  });

  it("an unrecognised verdict falls back to grey and shows the raw value", () => {
    render(<VerdictBanner verdict="SOMETHING_NEW" summary="s" />);
    expect(screen.getByRole("region", { name: "Verdict" })).toHaveAttribute("data-tone", "grey");
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("SOMETHING_NEW");
  });
});

describe("PipelineSteps", () => {
  it("renders the six steps in the server's order with status text and detail", () => {
    render(<PipelineSteps steps={makeReport().steps} />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.getAttribute("data-step"))).toEqual([
      "FILE_HASH",
      "TEXT_ROOT",
      "LOCALIZATION",
      "AUTHORIZATION",
      "CHAIN_CHECK",
      "SEMANTIC_ANALYSIS",
    ]);
    expect(items[0]).toHaveTextContent(/fail/i);
    expect(items[2]).toHaveTextContent("ALIGNMENT, 12 comparisons");
    expect(items[4]).toHaveTextContent(/pass/i);
  });

  it.each<[StepStatus, RegExp]>([
    ["PASS", /pass/i],
    ["FAIL", /fail/i],
    ["WARN", /warning/i],
    ["DONE", /done/i],
    ["SKIPPED", /skipped/i],
  ])("status %s is conveyed as text, not only colour", (status, pattern) => {
    render(<PipelineSteps steps={[{ name: "CHAIN_CHECK", status, detail: "why" }]} />);
    expect(screen.getByRole("listitem")).toHaveTextContent(pattern);
  });
});

describe("ChainProofPanel", () => {
  const check = CHAIN_OK;
  it("ok: shows a match and the tx as a link only when the explorer URL is http(s)", () => {
    render(
      <ChainProofPanel
        check={{ ...check, explorer_url: `https://explorer.example/tx/${check.tx_hash}` }}
        revision={REFERENCE}
      />,
    );
    expect(screen.getByText(/matches the on-chain record/i)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      `https://explorer.example/tx/${check.tx_hash}`,
    );
    expect(screen.getByText(/revision 5 \(v3\)/)).toBeInTheDocument();
  });

  it("never links a non-http explorer_url (javascript: etc.)", () => {
    render(
      <ChainProofPanel check={{ ...check, explorer_url: "javascript:alert(1)" }} revision={null} />,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("mismatch: shows the reason and each mismatch", () => {
    render(
      <ChainProofPanel
        check={{
          ...check,
          ok: false,
          reason: "RECORD_MISMATCH",
          mismatches: ["text_root differs"],
        }}
        revision={null}
      />,
    );
    expect(screen.getByText(/does not match/i)).toBeInTheDocument();
    expect(screen.getByText("text_root differs")).toBeInTheDocument();
  });

  it("not performed / absent: says so, without an error tone", () => {
    const { rerender } = render(
      <ChainProofPanel
        check={{ ...check, performed: false, ok: null, reason: "chain disabled", tx_hash: null }}
        revision={null}
      />,
    );
    expect(screen.getByText(/not performed: chain disabled/i)).toBeInTheDocument();
    rerender(<ChainProofPanel check={null} revision={null} />);
    expect(screen.getByText(/not performed/i)).toBeInTheDocument();
  });
});
