import { ethers, network } from "hardhat";

// Read-only: prints every VersionAnchored / VersionRevoked event of the registry.
// Usage: REGISTRY_ADDRESS=0x... npx hardhat run scripts/show-chain.ts --network localhost
async function main(): Promise<void> {
  const address = process.env.REGISTRY_ADDRESS?.trim();
  if (!address) throw new Error("Set REGISTRY_ADDRESS");
  const registry = await ethers.getContractAt("ProofChainRegistry", address);
  const block = await ethers.provider.getBlockNumber();
  console.log(`network=${network.name} registry=${address} latestBlock=${block}\n`);

  for (const ev of await registry.queryFilter(registry.filters.VersionAnchored())) {
    const a = ev.args;
    console.log(`block ${ev.blockNumber}  tx ${ev.transactionHash}`);
    console.log(`  ANCHORED v${a.versionNo}  docId=${a.docId}`);
    console.log(`  fileHash=${a.fileHash}`);
    console.log(`  textRoot=${a.textRoot}`);
    console.log(`  prevTextRoot=${a.prevTextRoot}  canon=${a.canonVersion}  at=${a.anchoredAt}\n`);
  }
  for (const ev of await registry.queryFilter(registry.filters.VersionRevoked())) {
    console.log(`block ${ev.blockNumber}  REVOKED v${ev.args.versionNo} docId=${ev.args.docId} reason="${ev.args.reason}"`);
  }
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
