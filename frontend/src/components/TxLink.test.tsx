import { render, screen } from "@testing-library/react";
import { TxLink } from "./TxLink";

const VALID_HASH = `0x${"a".repeat(64)}`;

describe("TxLink", () => {
  it("shows 'not recorded' text for a null tx hash", () => {
    render(<TxLink txHash={null} explorerBaseUrl="https://sepolia.etherscan.io/tx/" />);
    expect(screen.getByText("anchored (tx not recorded)")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders plain text when the tx hash does not match the expected format", () => {
    render(<TxLink txHash="not-a-real-hash" explorerBaseUrl="https://sepolia.etherscan.io/tx/" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText(/not-a-.*hash/)).toBeInTheDocument();
  });

  it("renders plain text when no explorer base URL is configured", () => {
    render(<TxLink txHash={VALID_HASH} explorerBaseUrl={undefined} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders plain text and never a link for a javascript: base URL", () => {
    render(<TxLink txHash={VALID_HASH} explorerBaseUrl="javascript:alert(1)//" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("links to the explorer when both the base URL and hash are valid", () => {
    render(<TxLink txHash={VALID_HASH} explorerBaseUrl="https://sepolia.etherscan.io/tx/" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", `https://sepolia.etherscan.io/tx/${VALID_HASH}`);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
