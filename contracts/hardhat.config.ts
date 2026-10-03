import "@nomicfoundation/hardhat-toolbox";
import type { HardhatUserConfig } from "hardhat/config";
import { envFilePaths, loadEnvFiles, networksFromEnv } from "./scripts/lib/env-lib";

// Repo-root .env first, contracts/.env as a fallback; real environment variables win over both.
loadEnvFiles(envFilePaths(__dirname));

const { ETHERSCAN_API_KEY, REPORT_GAS } = process.env;

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: networksFromEnv(process.env),
  gasReporter: {
    enabled: REPORT_GAS === "true",
    currency: "USD",
  },
  etherscan: { apiKey: ETHERSCAN_API_KEY ?? "" },
};

export default config;
