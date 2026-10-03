import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";

/** Repo-root `.env` first, then `contracts/.env` as a fallback (first file to set a variable wins). */
export function envFilePaths(contractsDir: string): string[] {
  return [
    path.resolve(contractsDir, "..", ".env"),
    path.resolve(contractsDir, ".env"),
  ];
}

/** Like dotenv.config for several files; never overrides a variable that is already set. */
export function loadEnvFiles(files: string[], target: NodeJS.ProcessEnv = process.env): void {
  for (const file of files) {
    if (!fs.existsSync(file)) continue;
    const parsed = dotenv.parse(fs.readFileSync(file));
    for (const [key, value] of Object.entries(parsed)) {
      if (target[key] === undefined) target[key] = value;
    }
  }
}

export interface NetworkEntry {
  url: string;
  chainId: number;
  accounts?: string[];
}

const set = (v: string | undefined): v is string => v !== undefined && v.trim() !== "";

export function networksFromEnv(env: NodeJS.ProcessEnv): Record<string, NetworkEntry> {
  const networks: Record<string, NetworkEntry> = {
    localhost: { url: "http://127.0.0.1:8545", chainId: 31337 },
  };
  const { SEPOLIA_RPC_URL, DEPLOYER_PRIVATE_KEY } = env;
  if (set(SEPOLIA_RPC_URL) && set(DEPLOYER_PRIVATE_KEY)) {
    networks.sepolia = {
      url: SEPOLIA_RPC_URL.trim(),
      chainId: 11155111,
      accounts: [DEPLOYER_PRIVATE_KEY.trim()],
    };
  }
  return networks;
}
