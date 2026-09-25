import { ethers, network, artifacts } from "hardhat";
import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "..", "..");

export interface DeployOptions {
  anchorAddress?: string;
  deploymentsDir?: string;
  abiPath?: string;
}

export interface DeployResult {
  address: string;
  record: Record<string, string | number> | null;
  wroteFiles: boolean;
}

export async function deployRegistry(opts: DeployOptions = {}): Promise<DeployResult> {
  if (opts.anchorAddress !== undefined && !ethers.isAddress(opts.anchorAddress)) {
    throw new Error(`ANCHOR_ADDRESS is not a valid address: ${opts.anchorAddress}`);
  }

  const [deployer] = await ethers.getSigners();
  const anchorer = opts.anchorAddress ?? deployer.address;

  const contract = await ethers.deployContract("ProofChainRegistry", [deployer.address, anchorer]);
  const receipt = await contract.deploymentTransaction()!.wait();
  if (!receipt) throw new Error("deployment transaction was not mined");
  const address = await contract.getAddress();

  const explicit = opts.deploymentsDir !== undefined || opts.abiPath !== undefined;
  if (network.name === "hardhat" && !explicit) {
    return { address, record: null, wroteFiles: false };
  }

  const deploymentsDir = opts.deploymentsDir ?? path.join(ROOT, "deployments");
  const abiPath =
    opts.abiPath ??
    path.resolve(ROOT, "..", "backend", "app", "chain", "abi", "ProofChainRegistry.json");

  const record = {
    address,
    chainId: Number((await ethers.provider.getNetwork()).chainId),
    deployer: deployer.address,
    blockNumber: receipt.blockNumber,
    txHash: receipt.hash,
    deployedAt: new Date().toISOString(),
  };
  fs.mkdirSync(deploymentsDir, { recursive: true });
  fs.writeFileSync(
    path.join(deploymentsDir, `${network.name}.json`),
    JSON.stringify(record, null, 2) + "\n",
  );

  const artifact = await artifacts.readArtifact("ProofChainRegistry");
  fs.mkdirSync(path.dirname(abiPath), { recursive: true });
  fs.writeFileSync(abiPath, JSON.stringify(artifact.abi, null, 2) + "\n");

  return { address, record, wroteFiles: true };
}
