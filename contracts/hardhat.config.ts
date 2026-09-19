import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";
import type { HardhatUserConfig } from "hardhat/config";

dotenv.config();

const { SEPOLIA_RPC_URL, DEPLOYER_PRIVATE_KEY, ETHERSCAN_API_KEY, REPORT_GAS } = process.env;

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: {
    localhost: { url: "http://127.0.0.1:8545", chainId: 31337 },
    ...(SEPOLIA_RPC_URL && DEPLOYER_PRIVATE_KEY
      ? {
          sepolia: {
            url: SEPOLIA_RPC_URL,
            chainId: 11155111,
            accounts: [DEPLOYER_PRIVATE_KEY],
          },
        }
      : {}),
  },
  gasReporter: {
    enabled: REPORT_GAS === "true",
    currency: "USD",
  },
  etherscan: { apiKey: ETHERSCAN_API_KEY ?? "" },
};

export default config;
