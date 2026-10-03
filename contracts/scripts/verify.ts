import { network, run } from "hardhat";
import * as path from "path";
import { verifyTarget } from "./lib/verify-lib";

async function main(): Promise<void> {
  const target = verifyTarget(
    path.resolve(__dirname, "..", "deployments"),
    network.name,
    process.env.ANCHOR_ADDRESS,
  );
  await run("verify:verify", target);
  console.log(`Verified ${target.address} on ${network.name}`);
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
