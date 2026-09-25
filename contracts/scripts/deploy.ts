import { deployRegistry } from "./lib/deploy-lib";

async function main(): Promise<void> {
  const anchorAddress = process.env.ANCHOR_ADDRESS?.trim() || undefined;
  const r = await deployRegistry({ anchorAddress });
  console.log(`ProofChainRegistry deployed to ${r.address}`);
  if (r.record) console.log(JSON.stringify(r.record, null, 2));
  console.log(`REGISTRY_ADDRESS=${r.address}`);
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
