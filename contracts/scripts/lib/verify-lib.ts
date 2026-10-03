import { ethers } from "ethers";
import * as fs from "fs";
import * as path from "path";

export interface DeploymentRecord {
  address: string;
  chainId: number;
  deployer: string;
  blockNumber: number;
  txHash: string;
  deployedAt: string;
}

/** Constructor args of ProofChainRegistry(admin, anchorer), as deploy-lib passed them. */
export function verifyArgs(record: DeploymentRecord, anchorAddress: string | undefined): string[] {
  const anchor = anchorAddress?.trim() || undefined;
  if (anchor !== undefined && !ethers.isAddress(anchor)) {
    throw new Error(`ANCHOR_ADDRESS is not a valid address: ${anchor}`);
  }
  return [record.deployer, anchor ?? record.deployer];
}

export function verifyTarget(
  deploymentsDir: string,
  networkName: string,
  anchorAddress: string | undefined,
): { address: string; constructorArguments: string[] } {
  const file = path.join(deploymentsDir, `${networkName}.json`);
  if (!fs.existsSync(file)) {
    throw new Error(`No deployment record ${networkName}.json in ${deploymentsDir}; deploy first`);
  }
  const record = JSON.parse(fs.readFileSync(file, "utf8")) as DeploymentRecord;
  return { address: record.address, constructorArguments: verifyArgs(record, anchorAddress) };
}
