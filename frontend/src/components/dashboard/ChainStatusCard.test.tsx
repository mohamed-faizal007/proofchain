import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { describe, expect, it } from "vitest";
import { api } from "../../api/client";
import type { ChainStatus } from "../../api/types";
import { ChainStatusCard } from "./ChainStatusCard";

const CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3";

function serve(reply: ChainStatus | "error"): void {
  api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
    if (config.url !== "/chain/status") return Promise.reject(new Error("unexpected"));
    if (reply === "error") return Promise.reject(new Error("boom"));
    return Promise.resolve({
      data: reply,
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    } as AxiosResponse);
  }) as AxiosAdapter;
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChainStatusCard />
    </QueryClientProvider>,
  );
}

describe("ChainStatusCard", () => {
  it("shows network, shortened contract with copy, latest block and a healthy indicator", async () => {
    serve({
      configured: true,
      healthy: true,
      chain_id: 31337,
      contract: CONTRACT,
      latest_block: 3,
    });
    renderCard();
    expect(await screen.findByText("Hardhat local")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("0x5FbD…0aa3")).toHaveAttribute("title", CONTRACT);
    expect(screen.getByRole("button", { name: "Copy contract address" })).toBeInTheDocument();
    expect(screen.getByText("#3")).toBeInTheDocument();
  });

  it("flags an unreachable node without hiding the last known details", async () => {
    serve({
      configured: true,
      healthy: false,
      chain_id: 11155111,
      contract: CONTRACT,
      latest_block: null,
    });
    renderCard();
    expect(await screen.findByText("Unreachable")).toBeInTheDocument();
    expect(screen.getByText("Sepolia testnet")).toBeInTheDocument();
  });

  it("says so when no chain client is configured", async () => {
    serve({
      configured: false,
      healthy: false,
      chain_id: null,
      contract: null,
      latest_block: null,
    });
    renderCard();
    expect(await screen.findAllByText("Not configured")).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: /copy contract/i })).not.toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    serve("error");
    renderCard();
    expect(await screen.findByRole("alert")).toHaveTextContent(/unavailable/i);
  });
});
